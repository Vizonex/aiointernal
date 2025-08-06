# aiointernal
This may or may not be the final name of this library the goal was
to make it so that users could implement a form of logic found in 
`aiosqlite` but allow this concept to be easily applied elsewhere.

The idea is this. A system of communication between objects that 
may or may not be threadsafe or may block and an asynchronous 
application without killing performance. This is different from 
`asyncio.to_thread` as this library assumes the object must remian 
in the same Thread a good example of this is a JavaScript intrepreter 
such as __pyduktape2__ where you need to intrepret HTML5 or another form 
of javascript without blocking other asynchronous tasks and allowing the 
Context to remain alive for further execution with it. 

Aiointernal is built around another library called Culsans for a Queue 
implementation between synchronous and asynchronous things.


```python
import asyncio
from pathlib import Path
from typing import Union

# In our example: this is the library we wish to make run 
# asynchronously, pyducktape2 is strict about threads and so 
# is the C Library, aiointernal's job is to respect it's wishes 
# without blocking the main eventloop. This way, we can safely
# Crack/Decrypt as much Javascript or Captchas as we want asyncrhonously. 

from pyduktape2 import DuktapeContext

from aiointernal import HeapThread, sync


class AioDuktapeContext(HeapThread):
    # Peform initalization on setup so that DuktapeContext 
    # doesn't throw an error for being ran from a different thread.

    def on_setup(self):
        self._context = DuktapeContext()

    # sync wrapper helps wrap functions we would like for this 
    # thread to use, and keep the context away 
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
    def bulk_eval_js(
        self, 
        src:list[Union[str, bytes]]
    ) -> Generator[None, Any, object]:
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

        # functions can be queued for later as long as they are 
        # all Generators this is due to not desiring to be wasteful 
        # or lacking communication with the eventloop
        
        fut = ctx.bulk_eval_js.queue([b'1 + 3', b'67 + 45']) # NOTE: this will transform into a List[object] due to its implementation.
        await fut

if __name__ == "__main__":
    asyncio.run(main())
```


