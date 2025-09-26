# %%
from asyncio import run, create_task, StreamReader, get_event_loop, StreamReaderProtocol, sleep
from random import randrange
import sys
import logging
from skr_mini import SKR_MINI
from agitators import Agitators
from pico import Picos
import time
import re
import csv
import os
from datetime import datetime

logging.basicConfig(filename='log.log', encoding='utf-8', level=logging.DEBUG)

# To calibrate the SKR's position set the x, y & z position of the "sensor_1_pickup_position" on line 10 of the file skr_mini.py
#%%

async def main():
    # To stop the script running hit enter
    create_task(cancel_on_enter_keypress())

    # Connects to the motion control board
    await skr.connect()

    await skr.home()

    # Move the head to the X & Y location of a sensor (plate, column, row)
    # await skr.move_to(0, 0, 0, True)

    # Move to, grab and raise a sensor from the rack
    # await skr.collect_sensor(0, 0, 0)

    # Return a sensor to the rack
    # await skr.dropoff_sensor(0, 0, 0)

    # Open the head's jaws
    # await skr.open_jaw()

    # move sensors about randomly
    # Make sure to set the starting "positions" below (Line 43)
    #await move_sensors_randomly()

    # print(await picos.check_connections())

    await skr.disconnect()
    # await picos.close()

# init 2x3x12 array to represent the positions a sensor can be in the well plate
positions = [[[False]*12 for _i in range(3)], [[False]*12 for _i in range(3)]]

positions[0][0][0] = True

def save_data_csv(data_dict, label, axes=('X', 'Y', 'Z')):
    """
    Save a dict of lists (e.g. {'X': [...], 'Y': [...], 'Z': [...]}) as a CSV with axis columns.
    Each row contains the i-th value from each axis list.
    """
    os.makedirs("DATA", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join("DATA", f"{label}_{timestamp}.csv")
    # Find the maximum length among all axis lists
    max_len = max(len(data_dict.get(axis, [])) for axis in axes)
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(axes)  # Write column labels
        for i in range(max_len):
            row = [data_dict.get(axis, [None]*max_len)[i] if i < len(data_dict.get(axis, [])) else "" for axis in axes]
            writer.writerow(row)
    print(f"Saved {label} data to {filename}")

def pick_random_position():
    plate = randrange(1)
    col = randrange(2)
    # row = randrange(12)
    row = randrange(6)

    return plate, col, row


def pick_random_sensor():
    position: tuple[int, int, int]
    while True:
        position = pick_random_position()
        plate, col, row = position
        if positions[plate][col][row]:
            break
    return position


def pick_random_destination():
    position: tuple[int, int, int]
    while True:
        position = pick_random_position()
        plate, col, row = position
        if not positions[plate][col][row]:
            break
    return position


async def cancel_on_enter_keypress():
    global close
    reader = StreamReader()
    pipe = sys.stdin
    loop = get_event_loop()
    await loop.connect_read_pipe(lambda: StreamReaderProtocol(reader), pipe)

    async for _line in reader:
        # print(f'Got: {line.decode()!r}')
        close = True
        await skr.disconnect()

async def get_axis_status(endstops=True, currents=True):
    """
    Returns a dict with axis currents and endstop status.
    Keys: 'X_current', 'Y_current', ..., 'X_end_stop', ...
    Values: float for current, bool for endstop triggered.
    """
    status = {}
    if endstops: await skr.check_endstops()
    if currents: await skr.check_currents()
    logs=skr.get_new_logs_since_last()
    # Endstop lines: e.g. 'x_min: TRIGGERED'
    endstop_pattern = re.compile(r'([xyza])_(min|max):\s*(TRIGGERED|open)', re.IGNORECASE)
    # Current lines: e.g. 'X driver current: 1500'
    current_pattern = re.compile(r'([XYZA]|I)\s*driver current:\s*([\d.]+)', re.IGNORECASE)

    for line in logs:
        # Endstop status
        match = endstop_pattern.match(line)
        if match:
            axis = match.group(1).upper()
            triggered = match.group(3).lower() == "triggered"
            status[f"{axis}_end_stop"] = triggered
            continue
        # Currents
        match = current_pattern.match(line)
        if match:
            axis = match.group(1).upper()
            value = float(match.group(2))
            status[f"{axis}_current"] = value
            continue

    return status


async def find_endstop_position(axis: str, current:int, step_coarse: float, step_fine: float, offset:float=0.0):
    """
    Moves up in mm along the given axis until end stop is triggered,
    backs off by 'backoff', then moves up in fine steps until triggered.
    Returns total distance moved until end stop.
    axis: 'X', 'Y', 'Z', or 'A'
    step_coarse: coarse step size in mm
    step_fine: fine step size in mm
    backoff: distance to back off after coarse trigger (default 2.0 mm)
    """
    start_pos = await skr.get_pos()
    start_pos = await skr.get_pos()
    pos:float = start_pos[axis]
    print(f"{axis}_pos start {pos:.2f}")
    if axis == 'X' or axis == 'Y':
        await skr.set_current_xy(current)
        speed = skr.xy_move_speed
    elif axis == 'Z':
        await skr.set_current_z(current)
        speed = skr.z_move_speed
    else:
        raise ValueError("Axis must be 'X', 'Y', or 'Z'")
    
    # Coarse approach
    i=0
    total_up = 0.00
    running_total = 0.00

    dir = -1
    if axis == 'Y':
        dir = 1 #y is inverted
        await skr.homex()

    if offset != 0:
        await skr._device.run([f"G1 {axis}{pos+dir*offset} F{speed}"])

    while True:
        i +=1

        status = await get_axis_status(True,False)  # check endstop status
        if status.get(f"{axis}_end_stop", True):
            break
        if i > 200:  # Safety to prevent infinite loop
            print(f"{axis} End stop not triggered within expected range.")
            return None
        total_up += step_coarse
        running_total = pos + dir*(total_up+offset)
        print(f"moving to {running_total}")
        await skr._device.run([f"G1 {axis}{running_total} F{speed}"])

    # Back off large hysteresis, so down far, back up to just before the last coarse step
    backoff = 5
    await skr._device.run([f"G1 {axis}{running_total- dir*backoff} F{speed}"])
    print(f"backing off to {running_total - dir*backoff}")
    running_total = running_total - dir*step_coarse*1.1
    print(f"return to {running_total}")
    await skr._device.run([f"G1 {axis}{running_total} F{speed}"])

    i=0
    # Fine approach
    while True:
        i +=1
        status = await get_axis_status(True,False)  # check endstop status
        if status.get(f"{axis}_end_stop", True):
            break
        if i > step_coarse*2/step_fine:  # Safety to prevent infinite loop
            print("End stop not triggered within coarse range.")
            return None
        running_total= running_total + dir*step_fine
        print(f"moving to {running_total}, step fine {step_fine}")
        await skr._device.run([f"G1 {axis}{running_total} F{speed}"])        
    
    travel = start_pos[axis]-running_total
    print("distance moved: ",start_pos[axis]-running_total)
    return travel

async def measure_co_ords(plate, column, row, offset, clearance, axes=["X", "Y", "Z"], repeats=3):
    """
    Measures distance to endstops for each axis at a given location.
    offset: list or dict of offsets for each axis.
    clearance: list or dict of clearances for each axis.
    Returns a dict of lists: {axis: [distance1, distance2, ...]}
    """
    data = {}
    direction_map = {'X': [-1, 1], 'Y': [1, -1], 'Z': [-1, 1]}
    current_map = {'X': 125, 'Y': 125, 'Z': 160}
    await skr._device.run(["M211 S0"])
    await skr.set_maxfeed(100000, 10000)
    await skr.set_acceleration_xy(20000)
    await skr.set_acceleration_z(1000)
    await skr.Stealth_chop(False)
    set_speed(3000, 500)

    for axis in axes:
        print (axis)
        data_axis = []
        direction = direction_map[axis]
        current = current_map[axis]
        axis_offset = offset[axes.index(axis)] if isinstance(offset, (list, tuple)) else offset.get(axis, 0)
        axis_clearance = clearance[axes.index(axis)] if isinstance(clearance, (list, tuple)) else clearance.get(axis, 0)

        for i in range(repeats):
            print(repeats, axis, i)
            await skr.set_current_xy(500)
            await skr.set_current_z(500)
            await skr.homezxy()
            await up()
            await skr.move_to_rel(plate, column, row, [-axis_clearance, axis_clearance])
            if axis != "Z":
                await skr.set_current_xy(current)
                print("down")
                await down(6)
            else:
                await skr.set_current_z(current)
            print("crash zone")
            await skr.move_to_rel(plate, column, row, [-axis_clearance*direction[0]*0.5, axis_clearance*direction[1]*0.5])
            if axis != "Z":
                await skr.set_current_z(500)
                await up()
            else:
                await down(6.5)
            print("about to measure distance")
            distance = await find_endstop_position(axis, 1000, 0.4, 0.05, axis_offset)
            print(f"Distance until {axis} end stop: {distance} mm")
            data_axis.append(distance)

        data[axis] = data_axis

    print(data)
    save_data_csv(data, f"data_{plate},{column},{row}")
    return data

def set_speed(xy, z):
    skr.xy_move_speed = xy
    skr.z_move_speed = z
    
async def up():
    await skr._ascend()

async def down(distance_above_plate = 6.5):
    await skr._descend(distance_above_plate)

async def access_left():
    await skr.move_to_safe(1, 0, 0, True)

async def access_right():
    await skr.move_to_safe(0, 0, 0, True)

async def move_sensors_randomly():
    while not close:
        plate1, col1, row1 = pick_random_sensor()
        plate2, col2, row2 = pick_random_destination()
        print(
            f"moving {plate1}, {col1}, {row1*2} to {plate2}, {col2}, {row2*2}")
        # await skr.move_sensor(plate1, col1, row1, plate2, col2, row2)
        await skr.collect_sensor(plate1, col1, row1)
        # values = await picos.check_connections()
        # if abs(values[0]) < 10000:
        #     break
        # print(values)

        await skr.dropoff_sensor(plate2, col2, row2)
        positions[plate1][col1][row1] = False
        positions[plate2][col2][row2] = True

        # await skr.home_jaw()

close = False

# %%
skr = SKR_MINI()
picos = Picos()
agitators = Agitators()
p = {'left':0, 'right':1}
c = {'left':0, 'right':1} #left A-D, and right E-H
#run(main())

#%%
#calibration delta002
'''
left_a1 = [3.3,31.2,22.6]
left_e1 = [39.3,31.2,22.6]
left_a12 = [3.3,130.2,22.6]
right_a1 = [107.5,31.3,22.6]
right_e1 = [143.7,31.3,22.6]
right_a12 = [107.1, 130.1, 22.6]
'''

left_a1 = [2.9,30.2,22.9]
left_e1 = [38.9,30.2,22.9]
left_a12 = [2.9,129.2,22.9]

right_a1 = [107,30.2,22.8]
right_e1 = [143,30.2,22.9]
right_a12 = [107,129.2,22.8]
#%%
skr.sensor_1_pickup_position = {"x": left_a1[0], "y": left_a1[1], "z": left_a1[2]}

#%%
Flex_map = {"X": 0.3, "Y": 0.6, "Z": 0.3}  # mm of flex on stall
Z_stall_height_to_rack_pick_up_height = 10.4  # mm
max_bed_y = 133

#%%
def pickup_postion_from_stall_co_ords(stall_coords_dict:dict, Flex_map=Flex_map, Z_stall_height_to_rack_pick_up_height=Z_stall_height_to_rack_pick_up_height, max_bed_y=max_bed_y) -> dict:
    """
    Given a dict with 'X', 'Y', 'Z' keys for stall coordinates,
    returns a dict with 'x', 'y', 'z' keys for pickup position.
    """
    pickup_position = {}
    stall_coords__mean_dict = {k: sum(v)/len(v) for k, v in stall_coords_dict.items()}
    for axis in ['X', 'Y', 'Z']:
        if axis in stall_coords__mean_dict:
            if axis == 'Z':
                print("Z", stall_coords__mean_dict[axis], Flex_map[axis], Z_stall_height_to_rack_pick_up_height)
                pickup_position[axis.lower()] = stall_coords__mean_dict[axis] - Flex_map[axis] + Z_stall_height_to_rack_pick_up_height
            elif axis =='Y':
                print("Y")
                pickup_position[axis.lower()] = max_bed_y + (stall_coords__mean_dict[axis] + Flex_map[axis])
            else:
                print("X")
                pickup_position[axis.lower()] = stall_coords__mean_dict[axis] - Flex_map[axis]
    # Adjust Z for rack pickup height
    return pickup_position

# %%
await skr.connect()
# %%
await skr.home()
#%%
await up()
await access_left()

#%%
await up()
await access_right()

#%%
set_speed(10000,2000)

#%%
await skr.check_endstops()
await skr.check_currents()

#%%
await skr.check_acceleration()

#%%
await skr._descend(30)


#%%
await down()
await up()

#%%
print(await get_axis_status())

await find_endstop_position('X', 1000, 1, 0.025)

#%%
await skr.home()

#%%
await skr.move_to_rel(0,0,10,[0,0,0])#z crash zone
#%%
data_z = []
await skr.move_to_rel(1,0,11,[3,-10,0])#z crash zone
await skr._device.run(["M211 S0"]) # turn off software endstops
await skr.set_maxfeed(100000,10000)
await skr.set_acceleration_z(1000)
set_speed(10000,500)

for i in range(20):
    await skr.set_current_z(153) #152 stalled, 153 hit.
    await down(6)
    distance = await find_endstop_position('Z', 1000, 1, 0.025)
    print(f"Distance until end stop: {distance} mm")
    data_z.append(distance)
    await skr.home_head()

print(data_z)
save_data_csv(data_z, "data_z")

#%%
#stall xy parameters
await skr._device.run(["M211 S0"]) # turn off software endstops
await skr.set_maxfeed(100000,10000)
await skr.set_acceleration_xy(20000)
set_speed(3000,500)
await skr.set_current_xy(150)
#await skr.move_to_rel(0,1,0,[-2,-1,10])
#await skr.move_to_rel(0,3,0,[-2,-1,10])

#%%
await skr.move_to_rel(1,0,4,[-10,-5])
await skr.move_to_rel(1,0,4,[-10,5])

for i in range(30):
    await skr.move_to_rel(1,0,4,[-10+i*0.5,-5])

#%%
axis = 'Y'
data  =[]
direction = [1,1]
clearance = [2,2]
offset = 90
await skr._device.run(["M211 S0"]) # turn off software endstops
await skr.set_maxfeed(100000,10000)
await skr.set_acceleration_xy(10000)
await skr.set_acceleration_z(1000)
set_speed(3000,500)

if axis == 'Y':
    direction = [1,-1]
if axis == 'X':
    direction = [-1,1]
if axis == 'Z':
    direction = [-1,1]

for i in range(3):
    await skr.set_current_xy(500) #152 stalled, 153 hit.
    await skr.homezxy()
    await up() #up to avoid crashes
    await skr.move_to_rel(1,0,0,[-clearance[0],clearance[1]])
    await down(6) #down to avoid
    await skr.set_current_xy(150) #drop current for crashing
    await skr.move_to_rel(1,0,0,[-clearance[0]*direction[0],clearance[1]*direction[1]])
    await skr.set_current_z(500)
    await up() #up to avoid crashes
    distance = await find_endstop_position(axis, 1000, 0.4, 0.05,offset)
    print(f"Distance until {axis} end stop: {distance} mm")
    data.append(distance)

print(data)
save_data_csv(data, f"data_{axis}")

#%%


#%%
'''

async def measure_co_ords(plate, column, row, offset, clearance, axes=["X", "Y", "Z"], repeats=1):
    data  = {}
    direction = [1,1]
    
    for axis in axes:
        data_axis = []
        if axis == 'Y':
            direction = [1,-1]
            offset = offset[1]
        if axis == 'X':
            direction = [-1,1]
            offset = offset[0]
        if axis == 'Z':
            direction = [-1,1]
            offset = offset[2]

        for i in range(repeats):
            await skr.set_current_xy(500) #152 stalled, 153 hit.
            await skr.homezxy()
            await skr._device.run(["M211 S0"]) # turn off software endstops
            await skr.set_maxfeed(100000,10000)
            await skr.set_acceleration_xy(10000)
            set_speed(3000,500)
            await up() #up to avoid crashes
            await skr.move_to_rel(plate,column,row,[-clearance[0],clearance[1]])
            await down(6) #down to avoid
            await skr.set_current_xy(150) #drop current for crashing
            await skr.move_to_rel(plate,column,row,[-clearance[0]*direction[0],clearance[1]*direction[1]])
            await skr.set_current_z(500)
            await up() #up to avoid crashes
            distance = await find_endstop_position(axis, 1000, 0.4, 0.05,offset)
            print(f"Distance until {axis} end stop: {distance} mm")
            data_axis.append(distance)

        data[axis]= data_axis

    print(data)
    save_data_csv(data, f"data_{plate},{column},{row}_{axis}")
    return data
'''
#%% front A1
pos_right_A1 = await measure_co_ords(1,0,0, [104,94,10], [2.2,2.2,2.2], axes=["X", "Y", "Z"], repeats=5)
PosrA1 = pickup_postion_from_stall_co_ords(pos_right_A1)
#%%
pos_right_A12 = await measure_co_ords(1,0,11, [104,1,10], [2.2,2.2,2.2], axes=["X", "Y", "Z"], repeats=5)
PosrA12 = pickup_postion_from_stall_co_ords(pos_right_A12)
#%%
data_y = []
for i in range(20):
    await skr.set_current_xy(500) #152 stalled, 153 hit.
    await up() #up to avoid crashes
    await skr.move_to_rel(1,0,0,[-2,-1])
    await down(6) #down to avoid
    await skr.set_current_xy(150) #drop current for crashing
    await skr.move_to_rel(1,0,0,[4,-1])
    await skr.set_current_z(500)
    await up()
    
    await skr.move_to_safe(1, 0, 0, False) #jaws closed
    await skr.move_to_rel(1,0,1,[-3,0,0]) #start behind row
    await down(6)
    await skr.set_current_xy(125) #152 stalled, 153 hit.
    await skr.move_to_rel(1,0,0,[-3,-4,0])
    distance = await find_endstop_position('Y', 1000, 1, 0.05,90)
    print(f"Distance until end stop: {distance} mm")
    data_y.append(distance)
    await skr.homex()
    await skr.homey()

print(data_y)
save_data_csv(data_y, "data_y")
#%%
data_y12 = []
#%%
for i in range(20):
    await skr.move_to_rel(1,0,11,[-3,3,0]) #start behind row
    await down(6)
    await skr.set_current_xy(125) #152 stalled, 153 hit.
    await skr.move_to_rel(1,0,11,[-3,-4,0])
    distance = await find_endstop_position('Y', 1000, 1, 0.05)
    print(f"Distance until end stop: {distance} mm")
    data_y12.append(distance)
    await skr.homex()
    await skr.homey()

print(data_y12)
save_data_csv(data_y12, "data_y12")
#%%
await skr.move_to_rel(1,0,5,[-3,-1,0])
#%%
await skr.set_current_xy(150)
await skr.move_to_safe(0, 0, 1, False) #jaws closed

#%%
await skr.homey()

#%%
await skr.set_current_xy(300)
await skr.home()

#%% 
await down(10)
#%%
await skr.set_current_z(153) #152 stalled, 153 hit.
await down(6)
await skr.set_current_z(500)
#%%
await skr.home_head()

# %%
await agitators.connect()


# %%
await skr.homezxy()

# %% Move the head to the X & Y location of a sensor (plate, column, row)

await skr.move_to_safe(0, 0, 0, True)

# %%
await agitators.start()
#%%
await agitators.stop_heating()

#%%
await agitators.stop()

#%% for calibration change first position, but afterwards push this into skr_mini
skr.sensor_1_pickup_position = {"x": left_a1[0], "y": left_a1[1], "z": left_a1[2]}
active_plate = p['left']
#skr.opening_offset = -2.5-0.625

#%%
pos_index = 13 -1

#%%
holes = 6 #left and right
z_hieght_piercing = 3.5 #distance above rack

#%% pokey pokey, can move to definition once tested
await skr.home()
await skr.collect_sensor(active_plate, c['left'], 0)

for hole in range(holes):
    x, y = await skr.move_to_safe(active_plate, pos_index % 2, (pos_index/2)//1, False) #front left plate 0 or 1, zigzag pattern
    print(x, y)
    old_z_speed = skr.z_move_speed
    skr.z_move_speed = 500
    await skr._descend(z_offset=z_hieght_piercing) #offset above rack
    x_coord = x- 1 #push flap
    y_coord = y
    cmds = [f'G1 X{x_coord} Y{y_coord} F{skr.xy_move_speed}']
    await skr._device.run(cmds)
    await skr.move_to(active_plate, pos_index % 2, (pos_index/2)//1, False)
    skr.z_move_speed = old_z_speed
    #time.sleep(1) # let hole be cut
    if False:
        shape = [1,0,-1,0] #x coord is index and y coord is +1 on index, so length of list is number of positions
        width = 1 #width of shape in mm modifies shape to real units
        for pos in range(len(shape)*2):
            x_coord = x + shape[pos%len(shape)]*width/2 #mod cycles through shape so that don't run off index
            y_coord = y + shape[(pos+1)%len(shape)]*width/2 #mod cycles through shape so that don't run off index
            cmds = [f'G1 X{x_coord} Y{y_coord} F{skr.xy_move_speed}']
            await skr._device.run(cmds)
            #time.sleep(1) # let agitation to open hole

        await skr.move_to_safe(active_plate, pos_index % 2, (pos_index/2)//1, False) #return to centre before ascent

    await skr._ascend() # to avoid crashing when moving
    pos_index += 1 # go to next position

await skr.dropoff_sensor(active_plate, c['left'], 0)
await skr.move_to_safe((active_plate+1)%2, 0, 11) #move to non active plate back left

# %% hold sensor in hole
skr.sensor_1_pickup_position = {"x": -2, "y": 1.5, "z": 20}
await skr.move_to_safe(1, 1, 0, False)

#%%
await skr.move_to_safe(1, 1, 0, True)
await skr.open_jaw()
await skr._descend()

# %% Move to, grab and raise a sensor from the rack
await skr.collect_sensor(active_plate, 0, 0)
await skr.move_to_safe((active_plate+1)%2, 0, 0, True)

# %% Return a sensor to the rack
await skr.move_to_safe(active_plate, 0, 0, True)
await skr._descend(z_offset=z_hieght_piercing)
# %%
await skr.dropoff_sensor(active_plate, 0, 0)
await skr.move_to_safe((active_plate+1)%2, 0, 0, True)

# %%
await skr.open_jaw()

    # move sensors about randomly
    # Make sure to set the starting "positions" below (Line 43)
    #await move_sensors_randomly()

    # print(await picos.check_connections())

# %%
await skr.disconnect()

# %%
await agitators.close()



# %%
pos = await skr.get_pos()

# %%
