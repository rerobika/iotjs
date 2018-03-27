# How to use C API to IoT.js module generator

This tool generates a module from a C API, and you can use it in IoT.js as other modules.

### Example:

#### Directory structure:

* iotjs/
* example_api/
  * foo/
    * foo.h
  * bar.h
  * libexample.a

#### Header files:

foo.h:
```c
int foo(int x); //return x+x
```

bar.h:
```c
void bar(); // print "Hello!"
```

#### Build:
```bash
# assuming you are in iotjs folder
# give library name without 'lib' prefix and '.a' suffix
$ tools/build.py --generate-module=../example_api/
```

#### Usage:
api.js:
```javascript
var lib = require('example_api_module');
var x = lib.foo(2);
console.log(x);                   // print 4
console.log(lib.bar());           // print 'Hello!'
```
