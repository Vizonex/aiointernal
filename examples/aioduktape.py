import asyncio
from pathlib import Path
from typing import Union, Generator, Any

# In our example: this is the library we wish to make run 
# asynchronously, pyducktape2 is strict about threads and so 
# is the C Library, aiointernal's job is to respect it's wishes 
# without blocking the main eventloop. 

from pyduktape2 import DuktapeContext

from aiointernal import HeapThread, sync


class AioDuktapeContext(HeapThread):
    # Peform initalization on setup so that DuktapeContext 
    # doesn't throw an error for being ran from a different thread.

    def on_setup(self):
        self._context = DuktapeContext()

    # sync wrapper helps wrap functions we would like for this 
    # thread to use, and keep the context in it's away 
    # from our main eventloop's thread. 

    @sync
    def set_globals(self, **kw) -> None:
        return self._context.set_globals(**kw)
    
    @sync
    def get_global(self, name:str) -> object:
        return self._context.get_global(name)
    
    @sync
    def eval_js(self, src: Union[str, bytes]) -> object:
        return self._context.eval_js(src)
    
    # This example can be queued becuase it's a generator making it easy
    # to cancel otherwise we would recieve a RuntimeError
    @sync 
    def bulk_eval_js(self, src:list[Union[str, bytes]]) -> Generator[None, Any, object]:
        """Custom function for demonstration of Generators"""
        for i in map(self._context.eval_js, src):
            yield i

    @sync
    def eval_js_file(self, src_path:Union[str, Path]) -> None:
        return self._context.eval_js_file(str(src_path))


async def main():
    async with AioDuktapeContext() as ctx:
        await ctx.eval_js("let item = 1 + 2;")
        item = await ctx.get_global("item")
        print(f"Got Number: {item} from Javascript")

        # functions can be queued for later so long as they are 
        # all Generators this is due to not desiring to be wasteful 
        # or lacking communication with the eventloop
        
        fut = ctx.bulk_eval_js.queue([b'1 + 3', b'67 + 45'])
        await fut



if __name__ == "__main__":
    asyncio.run(main())
