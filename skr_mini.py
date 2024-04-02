from marlin_serial_device import Device


class SKR_MINI:
    _device: Device
    column_spacing = 9*4
    # row_spacing = 9
    row_spacing = 18
    plate_spacing = 105.5
    sensor_1_pickup_position = {"x": 0.5, "y": 25.8, "z": 23.4}
    sensor_1_location = {"plate": 0, "column": 0, "row": 0}
    xy_move_speed = 7000
    z_move_speed = 500
    clearance_height = 0
    opening_distance = 5.5
    opening_offset = 2.2
    current_position = [0, 0, 0, 0]

    calibrate = False
    calibrated = False
    device_vid = "0483"
    line_end = "\r\n"

    def __init__(self):
        self._device = Device(self.device_vid)
        pass

    async def connect(self):
        await self._device.connect()

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

    async def open_jaw(self):
        await self._device.run([f'G1 A{self.opening_distance}'])

    async def _release_sensor(self, y: float):
        await self._device.run([f'G1 A{self.opening_distance} Y{y + self.opening_offset}'])

    async def _descend(self):
        await self._device.run([f'G1 Z{self.sensor_1_pickup_position["z"]} F{self.z_move_speed}'])

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

    async def _wait(self):
        await self._device.run(["M400"])

    async def grab_sensor(self, plate: int, column: int, row: int):
        _x, y = await self.move_to(plate, column, row, True)
        await self._descend()
        await self._grab_sensor(y)

    async def collect_sensor(self, plate: int, column: int, row: int):
        _x, y = await self.move_to(plate, column, row, True)
        await self.open_jaw()
        await self._descend()
        await self._grab_sensor(y)
        await self._ascend()

    async def dropoff_sensor(self, plate: int, column: int, row: int):
        _x, y = await self.move_to(plate, column, row, False)
        await self._descend()
        await self._release_sensor(y)
        await self._ascend()
        await self.close_jaw()

    async def home(self):
        cmds = ["G28 Z", "G28 A", "G28 X", "G28 Y"]
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
