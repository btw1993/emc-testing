from aioserial import AioSerial
from asyncio import Task, sleep, TaskGroup, create_task
import serial.tools.list_ports as list_ports
from InquirerPy import inquirer as inquirer
import logging

logger = logging.getLogger(__name__)


class Device:
    pid: str
    line_end = "\r\n"
    _serial: AioSerial
    _command_queue: list[str]
    _pending_commands = 0
    _close = False
    _tg: TaskGroup
    _listener_task: Task[None]
    _writer_task: Task[None]
    _buffer_size: int
    _timeout: float
    _baudrate: int

    def __init__(self, pid: str = "0483", baudrate: int = 115200, timeout: float = 0.5):
        self._buffer_size = 1
        self._command_queue = []
        self._baudrate = baudrate
        self._timeout = timeout
        self.pid = pid

    async def connect(self):
        ports = list(list_ports.grep(self.pid))
        port_names: list[str] = []
        for port in ports:
            port_names.append(port.device)
        if len(port_names) == 0:
            logger.warn(
                "Couldn't find a device. It might be in use or not connected")
            exit()
        if len(port_names) == 1:
            port_name = port_names[0]
        else:
            port_name = inquirer.select(
                message="Select a serial port", choices=port_names).execute()

        self._serial = AioSerial(port_name, 115200, timeout=0.5)

        self._listener_task = create_task(self._listen())
        self._writer_task = create_task(self._send_commands())

    def _should_keep_open(self):
        keep_open = (self._serial.is_open and not (
            self._close and self._pending_commands == 0))
        if (keep_open == False):
            logger.info("closing SKR...")
        return keep_open

    async def _listen(self):
        # Keep reading until either the serial port closes or we've finished sending commands and the input buffer is empty
        while self._should_keep_open():
            try:
                message = (await self._serial.readline_async()).decode().strip()
                if message:
                    logger.debug(f'SKR Reading: "{message}"')
                    if message.startswith("ok") and self._pending_commands > 0:
                        self._pending_commands -= 1
            except:
                pass
            await sleep(0.1)

    async def _send_commands(self):
        while self._should_keep_open():
            if self._pending_commands < self._buffer_size and len(self._command_queue):
                command = self._command_queue.pop(0)
                self._serial.write(
                    f"{command}{self.line_end}".encode())
                logger.debug(f'Sending: "{command}"')
                self._pending_commands += 1
            await sleep(0)

    async def run(self, commands: list[str]):
        for command in commands:
            self._command_queue.append(command)
            self._command_queue.append("M400")
        while (len(self._command_queue) > 0 or self._pending_commands) and not self._close:
            await sleep(0)

    async def run_as_file(self, commands: list[str], filename: str = "foo"):
        await self.run(["M110 0", f"M30 /{filename}.gco", f"M28 /{filename}.gco"])
        for i, command in enumerate(commands):
            formatted_cmd = self._format(command, i)
            print(formatted_cmd)
            self.send(formatted_cmd)
            await sleep(0.001)
        self.send("M29")
        await self.run(["M400"])

    def _format(self, command: str, line_number: int):
        cmd_with_line_number = f"N{line_number+1} {command}"
        checksum: int = 0
        for charachter in cmd_with_line_number:
            checksum ^= ord(charachter)

        return f"{cmd_with_line_number}*{str(checksum)}"

    def send(self, command: str):
        self._command_queue.append(command)

    async def close(self):
        if not self._close:
            self._close = True
            self._command_queue = ["M410"]
            while not self._listener_task.done():
                await sleep(0.1)
            await sleep(self._timeout + 0.1)
            self._serial.close()
