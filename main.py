# %%
from asyncio import run, create_task, StreamReader, get_event_loop, StreamReaderProtocol, sleep
from random import randrange
import sys
import logging
from skr_mini import SKR_MINI
from agitators import Agitators
from pico import Picos
import time

logging.basicConfig(filename='log.log', encoding='utf-8', level=logging.DEBUG)

# To calibrate the SKR's position set the x, y & z position of the "sensor_1_pickup_position" on line 10 of the file skr_mini.py


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

# %%
await skr.connect()

#%%
await skr.home_jaw()

await skr.open_jaw()

await skr.close_jaw()

# %%
await agitators.connect()

# %%
await skr.home()

# %% Move the head to the X & Y location of a sensor (plate, column, row)

await skr.move_to_safe(0, 0, 0, True)

# %%
await agitators.start()
#%%
await agitators.stop_heating()

#%%
await agitators.stop()

#%% for calibration change first position, but afterwards push this into skr_mini
skr.sensor_1_pickup_position = {"x": -1.8, "y": 1.2, "z": 20}
active_plate = p['right']
skr.opening_offset = -2.5-0.625

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
