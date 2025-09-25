from marlin_serial_device import Device
from asyncio import sleep
import re

class SKR_MINI:
    _device: Device
    column_spacing = 9*4
    row_spacing = 9
    #row_spacing = 18
    plate_spacing = 105.5
    sensor_1_pickup_position = {"x": -1.8, "y": 1.2, "z": 20}
    sensor_1_location = {"plate": 0, "column": 0, "row": 0}
    xy_move_speed = 7000
    z_move_speed = 500
    clearance_height = 0
    opening_distance = 5.0 #5.5 gamma3, 5 gamma4
    opening_offset = -2.5   #2.2 gamma3, -2.5 gamma4 reversed jaws
    current_position = [0, 0, 0, 0]
    calibrate = False
    calibrated = False
    device_vid = "0483"
    line_end = "\r\n"
    Current_logs = []

    def __init__(self):
        self._device = Device(self.device_vid)
        pass

    async def connect(self):
        await self._device.connect()

    def logs_list_all(self):
        return self._device.logs_list
    
    def get_new_logs_since_last(self):
        """
        Returns logs added since the last call to this function.
        """
        if not hasattr(self, "_last_log_index"):
            self._last_log_index = 0
        logs = self._device.logs_list
        new_logs = logs[self._last_log_index:]
        self._last_log_index = len(logs)
        return new_logs

    async def move_to(self, plate: int, column: int, row: int, offset: bool):
        x = self.sensor_1_pickup_position["x"]
        x += self.plate_spacing * (plate - self.sensor_1_location["plate"])
        x += self.column_spacing * (column - self.sensor_1_location["column"])

        y = self.sensor_1_pickup_position["y"]
        y += self.row_spacing * (row - self.sensor_1_location["row"])
        if offset:
            y += self.opening_offset

        cmds = [f'G1 X{x} Y{y} F{self.xy_move_speed}']
        # TODO check if device is connected
        # if self._device.
        await self._device.run(cmds)
        return x, y
    
    async def is_marlin_busy(self):
        logs = self.get_new_logs_since_last()
        for line in logs:
            if "busy: processing" in line:
                return True
        return False

    async def get_pos(self, timeout: float = 2.0, poll_interval: float = 0.025) -> dict:
        """
        Queries Marlin for the current position using M114 and parses the response.
        Waits up to 'timeout' seconds, polling every 'poll_interval' seconds.
        Returns a dict: {'X': float, 'Y': float, 'Z': float, 'A': float}
        """
        # Flush stale log entries so we parse the response to this M114
        self.get_new_logs_since_last()
        await self._device.run(['M114'])
        elapsed = 0
        pos_pattern = re.compile(r'X:([\d\.\-]+)\s+Y:([\d\.\-]+)\s+Z:([\d\.\-]+)\s+A:([\d\.\-]+)', re.IGNORECASE)
        while elapsed < timeout:
            await sleep(poll_interval)
            logs = self.get_new_logs_since_last()
            for line in logs:
                match = pos_pattern.search(line)
                if match:
                    return {
                        'X': float(match.group(1)),
                        'Y': float(match.group(2)),
                        'Z': float(match.group(3)),
                        'A': float(match.group(4))
                    }
            elapsed += poll_interval
        raise TimeoutError("Position not found in logs after M114")

    async def move_to_rel(self, plate: int, column: int, row: int, offsetxy:list):
        x = self.sensor_1_pickup_position["x"]
        x += self.plate_spacing * (plate - self.sensor_1_location["plate"])
        x += self.column_spacing * (column - self.sensor_1_location["column"])

        y = self.sensor_1_pickup_position["y"]
        y += self.row_spacing * (row - self.sensor_1_location["row"])

        cmds = [f'G1 X{x+offsetxy[0]} Y{y+offsetxy[1]} F{self.xy_move_speed}']
        # TODO check if device is connected
        # if self._device.
        await self._device.run(cmds)
        return x, y
    
    async def move_rel_z(self, up): #positive up, negative down, default for amperia is opposite
        start_pos = await self.get_pos()
        await self._device.run([f"G1 Z{start_pos['Z']-up} F{self.z_move_speed}"])
    
    async def move_to_safe(self, plate: int, column: int, row: int, offset: bool = True):
        await self._ascend()
        x, y = await self.move_to(plate, column, row, offset)
        return x, y

    async def open_jaw(self):
        await self._device.run([f'G1 A{self.opening_distance}'])
    
    async def Stealth_chop(self, enable: bool):
        if enable:
            await self._device.run([f'M569 S0'])
        else:
            await self._device.run([f'M569 S1'])
        

    async def _release_sensor(self, y: float):
        await self._device.run([f'G1 A{self.opening_distance} Y{y + self.opening_offset}'])

    async def _descend(self, z_offset:float = 0):
        z = self.sensor_1_pickup_position["z"]-z_offset
        await self._device.run([f'G1 Z{z} F{self.z_move_speed}'])

    async def close_jaw(self):
        await self._device.run([f'G1 A0'])

    async def _grab_sensor(self, y: float):
        await self._device.run([f'G1 A0 Y{y - self.opening_offset}'])

    async def _nudge_descend(self, y: float):
        await self._device.run([f'G1 A{self.opening_distance -1} Y{y-1}'])
        await self._device.run([f'G1 Z{self.sensor_1_pickup_position["z"]-3.8} F{self.z_move_speed}'])
        await self._device.run([f"G1 A{self.opening_distance} Y{y}"])
        await self._device.run([f'G1 Z{self.sensor_1_pickup_position["z"]} F{self.z_move_speed}'])

    async def _ascend(self):
        await self._device.run([f"G1 Z{self.clearance_height} F{self.z_move_speed}"])

    async def _wait(self): #for all G-code in buffer to be completed
        await self._device.run(["M400"])

    async def grab_sensor(self, plate: int, column: int, row: int):
        _x, y = await self.move_to(plate, column, row, True)
        await self._descend()
        await self._grab_sensor(y)

    async def collect_sensor(self, plate: int, column: int, row: int):
        _x, y = await self.move_to_safe(plate, column, row, True)
        await self.open_jaw()
        await self._descend()
        await self._grab_sensor(y)
        await self._ascend()

    async def dropoff_sensor(self, plate: int, column: int, row: int):
        _x, y = await self.move_to_safe(plate, column, row, False)
        await self._descend()
        await self._release_sensor(y)
        await self._ascend()
        await self.close_jaw()

    async def home(self):
        cmds = ["G28 Z", "G28 A", "G28 X", "G28 Y"]
        await self._device.run(cmds)

    async def set_current_xy(self, current: int):
        cmds = [f"M906 X{current} Y{current}"]
        await self._device.run(cmds)

    async def check_endstops(self):
        cmds = ["M119"]
        await self._device.run(cmds)
    
    async def check_currents(self):
        cmds = ["M906"]
        await self._device.run(cmds)
    
    async def check_acceleration(self):
        cmds = ["M503"]
        await self._device.run(cmds)

    async def set_acceleration_xy(self, acc):       
        cmds = [f"M201 X{int(acc*1.1)} Y{int(acc*1.1)}"]
        await self._device.run(cmds)
        cmds = [f"M204 P{acc} R{acc} T{acc}"]
        await self._device.run(cmds)

    async def set_acceleration_z(self, acc:int):       
        cmds = [f"M201 Z{int(acc*1.1)}"]
        await self._device.run(cmds)
        cmds = [f"M204 P{acc} R{acc} T{acc}"]
        await self._device.run(cmds)

    async def set_maxfeed(self, feedxy:int, feedz:int):       
        cmds = [f"M203 X{int(feedxy)} Y{int(feedxy)} Z{int(feedz)}"]
        await self._device.run(cmds)
    
    async def set_current_z(self, current: int):
        cmds = [f"M906 Z{current}"]
        await self._device.run(cmds)

    async def homezxy(self):
        cmds = ["G28 Z", "G28 X", "G28 Y"]
        await self._device.run(cmds)

    async def homex(self):
        cmds = ["G28 X"]
        await self._device.run(cmds)

    async def homey(self):
        cmds = ["G28 Y"]
        await self._device.run(cmds)

    async def home_head(self):
        cmds = ["G28 Z", "G28 A"]
        await self._device.run(cmds)

    async def home_jaw(self):
        cmds = ["G28 A"]
        await self._device.run(cmds)

    async def upload_circular_move_file(self, repeats: int = 10000):
        cmds = ["G28 Z", "G28 A", "G28 X", "G28 Y", f"G1 X60 Y110"]
        loops_cmds = [f"G2 I50 F{self.xy_move_speed}"]
        for _i in range(repeats):
            cmds += loops_cmds
        await self._device.run_as_file(cmds)

    async def run_circular_move(self):
        cmds = ["M23 CIRCLE.GCO", "M24"]
        await self._device.run(cmds)

    async def run_home_move_loop(self):
        cmds = ["M23 HOMEM.GCO", "M24"]
        await self._device.run(cmds)

    async def move_sensor(self, plate1: int, column1: int, row1: int, plate2: int, column2: int, row2: int):
        await self.collect_sensor(plate1, column1, row1)
        await self.dropoff_sensor(plate2, column2, row2)

    async def disconnect(self):
        await self._device.close()


