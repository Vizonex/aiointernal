from aiointernal import HeapThread, sync
from pathlib import Path
import pytest
import os



class AsyncTempFile(HeapThread):
    """Asynchronous implementation of a Reading & Writing to a Temporary File
    and destorying on close"""
    def __init__(self, filename:str, heap_size = 0, exception_handler = None):
        super().__init__(heap_size, exception_handler=exception_handler)
        self.filename = Path(filename)
        self._temp = None

    def on_setup(self):
        # ensure the file we want to work with at least exists
        with open(self.filename, "w") as f:
            f.write(" ")
            f.seek(0)

    def on_shutdown(self):
        os.remove(self.filename)

    @sync
    def write_text(self, text:str) -> int:
        return self.filename.write_text(text)

    @sync
    def read_bytes(self) -> bytes:
        return self.filename.read_bytes()


@pytest.mark.anyio
async def test_in_and_out_writing():
    async with AsyncTempFile("aiointernal.txt") as tmp:
        await tmp.write_text("testing-1-2-3")
        assert await tmp.read_bytes() == b"testing-1-2-3"
        assert os.path.exists("aiointernal.txt")
    assert not os.path.exists("aiointernal.txt")
    


