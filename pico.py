from aioserial import AioSerial
import aioserial
import time
import logging
from asyncio import Task, sleep, TaskGroup, create_task, run
import serial.tools.list_ports as list_ports
from InquirerPy import inquirer as inquirer

logger = logging.getLogger()


class Pico:

    SIP_FACTOR = {
        "a": 1e-18,
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        " ": 1.0,
        "i": 1.0,
        "k": 1e3,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
        "P": 1e15,
        "E": 1e18,
    }
    # 1027 for pico
    # _picos: list[AioSerial]
    port: str
    _serial: AioSerial
    _baudrate: int
    _command_queue: list[str]
    # _pending_commands = 0
    _close = False
    _tg: TaskGroup
    _listener_task: Task[None]
    _writer_task: Task[None]
    # _buffer_size = 1
    _timeout: float
    pico_index: int
    _check_connection_responses: list[float]
    _checking_connection: bool

    def __init__(self, port: str, index: int):
        self._baudrate = 230400
        self._timeout = 0.5
        self._checking_connection = False
        self._command_queue = []
        self.pico_index = index
        self.port = port

    async def connect(self):
        self._serial = AioSerial(
            self.port, self._baudrate, timeout=self._timeout, bytesize=aioserial.EIGHTBITS, parity=aioserial.PARITY_NONE,
            stopbits=aioserial.STOPBITS_ONE, xonxoff=False, rtscts=False, dsrdtr=False)

        self._listener_task = create_task(self._listen())
        self._writer_task = create_task(self._send_commands())

    async def _listen(self):
        # Keep reading until either the serial port closes or we've finished sending commands and the input buffer is empty
        while self._should_keep_open():
            try:
                message = (await self._serial.readline_async()).decode('ascii').strip()
                if message:
                    logger.debug(f'Reading on {self.pico_index}: "{message}"')
                if self._checking_connection and message.startswith('P'):
                    try:
                        response = self.parse_response(message)
                        if response is not None:
                            self._check_connection_responses.append(response)
                    except Exception as _e:
                        # self._logger.info(
                        #     f"Bad Data! {pico_response}, Exception raised:\n{e}")
                        continue
            except:
                pass
            await sleep(0.1)

    async def _send_commands(self):
        while self._should_keep_open():
            if len(self._command_queue):
                command = self._command_queue.pop(0)
                await self._serial.write_async(bytes(command + "\n", "ascii"))
                logger.debug(f'Sending on {self.pico_index}: "{command}"')
                # self._pending_commands += 1
            await sleep(0)

    def _should_keep_open(self):
        keep_open = (self._serial.is_open and not
                     (self._close and len(self._command_queue) == 0))
        if (keep_open == False):
            logger.info(f"closing pico {self.pico_index}...")
        return keep_open

    async def run(self, commands: list[str]):
        for command in commands:
            self._command_queue.append(command)
        while len(self._command_queue) > 0 and not self._close:
            await sleep(0)

    def send(self, command: str):
        self._command_queue.append(command)

    async def close(self):
        if not self._close:
            self._close = True
            while not self._listener_task.done():
                await sleep(0)
            while not self._writer_task.done():
                await sleep(0)
            await sleep(self._timeout + 0.1)
            self._serial.close()

    def parse_response(self, response: str):
        raw_value = -(int(response[3:10], 16) - 2**27)
        if (len(response) == 11):
            return raw_value * self.SIP_FACTOR[response[10]]*1e9
        if (len(response) == 10):
            return raw_value

    async def check_connection(self):
        cmds = self._get_calibration_template()
        await self.run(cmds)
        self._check_connection_responses = []
        self._checking_connection = True
        self._check_start_time = time.time()
        await sleep(3)
        self.send("Z")
        self._checking_connection = False

        if (len(self._check_connection_responses) > 0):

            value = sum(self._check_connection_responses) / \
                len(self._check_connection_responses)
        else:
            # TODO: Error
            value = 0
        dt = time.time() - self._check_start_time

        return value, dt

    async def start_read(self):
        cmds = self._get_calibration_template()
        await self.run(cmds)

    def _get_calibration_template(self) -> list[str]:
        return [
            "e",    # e command puts device in MethodSCRIPT mode
            "var p",    # Variable for set potential
            "var c",    # Variable for output current of main WE
            "set_pgstat_chan 1",    # Target channel 1
            "set_pgstat_mode 5",    # Set selected channel to bipot mode
            # Set bipot mode to fixed (0) or offset (1)
            "set_poly_we_mode 1",
            # Set offset or constant voltage (10mV offset from WE0) source drain
            "set_e 5m",
            "set_cr 100m",  # Set current range of secondary WE to 100uA
            "set_pgstat_chan 0",    # Select channel 0
            "set_pgstat_mode 2",    # Low speed mode
            "set_cr 100m",  # Set current range to 100uA
            "set_pot_range 0m 0m",  # Chronoamperometry does not need a pot range
            "set_max_bandwidth 500",    # Set bandwidth
            "set_e 0m",    # Set potential between WE and RE reference
            "set_gpio_cfg 0b11111 1",
            "set_gpio_pullup 0b11111 1",
            "set_gpio 0b11111i",
            "cell_on",  # Activate cell
            "wait 1",   # Wait a second for cell to stabilize
            "meas_loop_ca p c 0 100m 86400",    # Start loop
            # Stat data package without metadata
            "pck_start meta_msk(0x00)",
            "pck_add c",    # Add WE0 current output to data package
            "pck_end",
            "endloop",
            "on_finished:",
            "cell_off",
            "set_gpio 0b00000i",  # Disable FET
            ""  # Every MethodSCRIPT must terminate with newline character
        ]


class Picos:
    _picos: list[Pico]
    _num_picos = 4
    _pico_vid = "1027"

    async def connect(self):
        available_ports = list(list_ports.comports())
        ports = [port[0]
                 for port in available_ports if self._pico_vid in str(port.vid)]
        if len(ports) == 0:
            logger.warn(
                "Couldn't find any picos. They might be in use or not connected")
            exit()
        if len(ports) < self._num_picos:
            logger.warn(f"Only found {len(ports)} of 4 picos")
            exit()

        self._picos = [Pico(port, i) for i, port in enumerate(ports)]
        for pico in self._picos:
            await pico.connect()

    async def check_connections(self):
        tasks: list[Task[tuple[float, float]]] = []
        async with TaskGroup() as tg:
            for pico in self._picos:
                tasks.append(tg.create_task(pico.check_connection()))

        results: list[float] = []
        for _i, task in enumerate(tasks):
            value, _time = task.result()
            # results.append(value > 200)
            results.append(value)

        return results

    async def start_read(self):
        for pico in self._picos:
            await pico.start_read()

    async def close(self):
        closing: list[Task[None]] = []
        for pico in self._picos:
            closing.append(create_task(pico.close()))

        for task in closing:
            await task


async def main():
    picos = Picos()
    await picos.connect()
    await picos.check_connections()
    await picos.close()


# run(main())
