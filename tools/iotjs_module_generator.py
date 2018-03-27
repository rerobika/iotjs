#!/usr/bin/env python

# Copyright 2015-present Samsung Electronics Co., Ltd. and other contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys

from pycparser import c_parser, c_ast, parse_file, c_generator
from common_py import path
from common_py.system.filesystem import FileSystem as fs

C_VOID_TYPE = 'void'

C_BOOL_TYPE = '_Bool'

C_NUMBER_TYPES = [
    'short',
    'short int',
    'signed short',
    'signed short int',
    'unsigned short',
    'unsigned short int',
    'int',
    'signed',
    'signed int',
    'unsigned',
    'unsigned int',
    'long',
    'long int',
    'signed long',
    'signed long int',
    'unsigned long',
    'unsigned long int',
    'long long',
    'long long int',
    'signed long long',
    'signed long long int',
    'unsigned long long',
    'unsigned long long int',
    'float',
    'double',
    'long double',
]

C_CHAR_TYPES = [
    'char',
    'signed char',
    'unsigned char'
]

C_STRING_TYPES = [
    'char*',
    'signed char*',
    'unsigned char*'
]

INCLUDE = '''
#include "jerryscript.h"
#include "{HEADER}"
'''

JS_FUNC_HANDLER = '''
jerry_value_t {NAME}_handler (const jerry_value_t function_obj,
                              const jerry_value_t this_val,
                              const jerry_value_t args_p[],
                              const jerry_length_t args_cnt)
{{
{BODY}
}}
'''

JS_CHECK_ARG_COUNT = '''
  if (args_cnt != {COUNT})
  {{
    const char* msg = "Wrong argument count for {FUNC}(), expected {COUNT}.";
    return jerry_create_error(JERRY_ERROR_TYPE, (const jerry_char_t*)msg);
  }}
'''

JS_CHECK_ARG_TYPE = '''
  if (!jerry_value_is_{TYPE} (args_p[{INDEX}]))
  {{
    const char* msg = "Wrong argument type for {FUNC}(), expected {TYPE}.";
    return jerry_create_error(JERRY_ERROR_TYPE, (const jerry_char_t*)msg);
  }}
'''

JS_GET_NUM_ARG = '''
  {TYPE} arg_{INDEX} = jerry_get_number_value (args_p[{INDEX}]);
'''

JS_GET_BOOL_ARG = '''
  bool arg_{INDEX} = jerry_get_boolean_value (args_p[{INDEX}]);
'''

JS_GET_CHAR_ARG = '''
  jerry_char_t char_{INDEX}[1];
  jerry_string_to_char_buffer (args_p[{INDEX}], char_{INDEX}, 1);
  {TYPE} arg_{INDEX} = ({TYPE})char_{INDEX}[0];
'''

JS_NATIVE_CALL = '''
  {RETURN}{RESULT}{NATIVE}({PARAM});
'''

JS_FUNC_RET = '''
  return jerry_create_{TYPE}({RESULT});
'''

JS_REGIST_FUNC = '''
void register_function (jerry_value_t object,
                        const char* name,
                        jerry_external_handler_t handler)
{
  jerry_value_t prop_name = jerry_create_string((const jerry_char_t*)name);
  jerry_value_t func = jerry_create_external_function(handler);
  jerry_value_t ret = jerry_set_property(object, prop_name, func);
  jerry_release_value(prop_name);
  jerry_release_value(func);
  jerry_release_value(ret);
}
'''

JS_GET_PROP = '''
  jerry_value_t {s}_{m}_name = jerry_create_string ((const jerry_char_t *) "{m}");
  jerry_value_t {s}_{m}_value = jerry_get_property ({obj}, {s}_{m}_name);
  jerry_release_value({s}_{m}_name);
'''
INIT_FUNC = '''
jerry_value_t Init{NAME}()
{{
  jerry_value_t object = jerry_create_object();
{BODY}
  return object;
}}
'''

INIT_REGIST_FUNC = '''  register_function(object, "{NAME}", {NAME}_handler);
'''

MODULES_JSON = '''
{{
  "modules": {{
    "{NAME}_module": {{
      "native_files": ["{NAME}_js_wrapper.c"],
      "init": "Init{NAME}",
      "cmakefile": "module.cmake"
    }}
  }}
}}
'''

MODULE_CMAKE = '''
set(MODULE_NAME "{NAME}_module")
link_directories(${{MODULE_DIR}})
list(APPEND MODULE_LIBS {LIBRARY})
'''

class IdentifierType_Visitor(c_ast.NodeVisitor):
    def __init__(self):
        self.idtypes = []

    def visit_IdentifierType(self, node):
        self.idtypes.append(node)


class Struct_Visitor(c_ast.NodeVisitor):
    def __init__(self):
        self.structs = []

    def visit_Struct(self, node):
        if node.decls:
            self.structs.append(node)


class TypeDecl_Visitor(c_ast.NodeVisitor):
    def __init__(self):
        self.type = ''

    def visit_TypeDecl(self, node):
        if type(node.type) is c_ast.IdentifierType:
            self.type = (' ').join(node.type.names)
        elif type(node.type) is c_ast.Struct:
            if node.type.name:
                self.type = 'struct ' + node.type.name
            else:
                self.type = node.declname
        elif type(node.type) is c_ast.Enum:
            if node.type.name:
                self.type = 'enum ' + node.type.name
            else:
                self.type = node.declname
        elif type(node.type) is c_ast.Union:
            if node.type.name:
                self.type = 'union ' + node.type.name
            else:
                self.type = node.declname



def get_typedefs(ast):
    typedefs = []

    for decl in ast.ext:
        if type(decl) is c_ast.Typedef:
            typedefs.append(decl)

    return typedefs


def get_structs(ast):
    struct_visitor = Struct_Visitor()
    struct_visitor.visit(ast)
    return struct_visitor.structs


def get_functions(ast):
    funcs = []

    for decl in ast.ext:
        if type(decl) is c_ast.Decl and type(decl.type) is c_ast.FuncDecl:
            funcs.append(decl)

    return funcs


def get_params(functions):
    params = []

    for func in functions:
        if func.type.args:
            params += func.type.args.params

    return params


def resolve_typedefs(firstlist, secondlist):
    for first in firstlist:
        for second in secondlist:
            parent = second
            child = second.type

            while (type(child) is not c_ast.TypeDecl and
                   hasattr(child, 'type')):
                   parent = child
                   child = child.type

            if (type(child) is c_ast.TypeDecl and
                type(child.type) is c_ast.IdentifierType and
                [first.name] == child.type.names):
                parent.type = first.type


def generate_jerry_functions(functions):
    for function in functions:
        funcname = function.name
        funcdecl = function.type
        paramlist = funcdecl.args
        ret = funcdecl.type
        jerry_function = []
        native_params = []

        if paramlist:
            params = paramlist.params
            jerry_function.append(JS_CHECK_ARG_COUNT.format(COUNT=len(params),
                                                            FUNC=funcname))

            for index, param in enumerate(params):
                native_params.append('arg_' + str(index))

                if type(param.type) is c_ast.TypeDecl:
                    if type(param.type.type) is c_ast.IdentifierType:
                        paramtype = (' ').join(param.type.type.names)

                        if paramtype in C_NUMBER_TYPES:
                            jerry_function.append(JS_CHECK_ARG_TYPE.format(TYPE='number',
                                                                           INDEX=index,
                                                                           FUNC=funcname))
                            jerry_function.append(JS_GET_NUM_ARG.format(TYPE=paramtype,
                                                                        INDEX=index))
                        elif paramtype in C_CHAR_TYPES:
                            jerry_function.append(JS_CHECK_ARG_TYPE.format(TYPE='string',
                                                                           INDEX=index,
                                                                           FUNC=funcname))
                            jerry_function.append(JS_GET_CHAR_ARG.format(TYPE=paramtype,
                                                                         INDEX=index))
                        elif paramtype == C_BOOL_TYPE:
                            jerry_function.append(JS_CHECK_ARG_TYPE.format(TYPE='boolean',
                                                                           INDEX=index,
                                                                           FUNC=funcname))
                            jerry_function.append(JS_GET_BOOL_ARG.format(INDEX=index))

                    elif type(param.type.type) is c_ast.Struct:
                        struct = param.type.type
                        jerry_function.append(JS_CHECK_ARG_TYPE.format(TYPE='object',
                                                                       INDEX=index,
                                                                       FUNC=funcname))

                        for decl in struct:
                            jerry_function.append(JS_GET_PROP.format(s=struct.name,
                                                                     m=decl.name,
                                                                     obj='args_p['+str(index)+']'))

                            if type(decl.type) is c_ast.TypeDecl:
                                if type(decl.type.type) is c_ast.IdentifierType:
                                    membertype = (' ').join(decl.type.type.names)
                    elif type(param.type.type) is c_ast.Union:
                        pass
                    elif type(param.type.type) is c_ast.Enum:
                        pass
                elif type(param.type) is c_ast.PtrDecl:
                    pass

        native_params = (', ').join(native_params)

        if type(ret) is c_ast.TypeDecl:
            if type(ret.type) is c_ast.IdentifierType:
                returntype =(' ').join(ret.type.names)

                if returntype == C_VOID_TYPE:
                    jerry_function.append(
                        JS_NATIVE_CALL.format(RETURN='',
                                              RESULT='',
                                              NATIVE=funcname,
                                              PARAM=native_params))
                    jerry_function.append(JS_FUNC_RET.format(TYPE='undefined',
                                                             RESULT=''))
                else:
                    jerry_function.append(
                        JS_NATIVE_CALL.format(RETURN=returntype,
                                              RESULT=' result = ',
                                              NATIVE=funcname,
                                              PARAM=native_params))
                    if returntype in C_NUMBER_TYPES:
                        jerry_function.append(JS_FUNC_RET.format(TYPE='number',
                                                                 RESULT='result'))
                    elif returntype in C_CHAR_TYPES:
                        jerry_function.append(
                            JS_FUNC_RET.format(TYPE='string',
                                               RESULT='(jerry_char_ptr_t)(&result)'))
                    elif returntype == C_BOOL_TYPE:
                        jerry_function.append(JS_FUNC_RET.format(TYPE='boolean',
                                                                 RESULT='result'))

            elif type(ret.type) is c_ast.Struct:
                pass
            elif type(ret.type) is c_ast.Union:
                pass
            elif type(ret.type) is c_ast.Enum:
                pass

        yield JS_FUNC_HANDLER.format(NAME=funcname,
                                     BODY=('\n').join(jerry_function))


def gen_c_source(header, dirname):

    preproc_args = ['-Dbool=_Bool',
                    '-D__attribute__(x)=',
                    '-D__asm__(x)=',
                    '-D__restrict=restrict',
                    '-D__builtin_va_list=void']

    ast = parse_file(header, use_cpp=True, cpp_args=preproc_args)

    functions = get_functions(ast)
    typedefs = get_typedefs(ast)
    params = get_params(functions)

    resolve_typedefs(typedefs, typedefs)
    resolve_typedefs(typedefs, functions)
    resolve_typedefs(typedefs, params)

    generated_source = [
        INCLUDE.format(HEADER=dirname + '_js_wrapper.h'),
        JS_REGIST_FUNC
        ]

    for jerry_function in generate_jerry_functions(functions):
        generated_source.append(jerry_function)

    init_function = []
    for function in functions:
        init_function.append(INIT_REGIST_FUNC.format(NAME=function.name))

    generated_source.append(INIT_FUNC.format(NAME=dirname,
                                             BODY=('\n').join(init_function)))

    return ('\n').join(generated_source)


def gen_header(directory):
    includes = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.h'):
                includes.append('#include "' +
                                os.path.abspath(os.path.join(root, file)) +
                                '"')

    return ('\n').join(includes)


def create_header_to_parse(header_name, copy_dir):
    header_text = gen_header(copy_dir)
    with open(header_name, 'w') as tmp:
        tmp.write(header_text)

    preproc_args = ['-Dbool=_Bool',
                    '-D__attribute__(x)=',
                    '-D__asm__(x)=',
                    '-D__restrict=restrict',
                    '-D__builtin_va_list=void']

    ast = parse_file(header_name, use_cpp=True, cpp_args=preproc_args)
    typedefs = get_typedefs(ast)
    structs = get_structs(ast)
    ast = c_ast.FileAST(typedefs + structs)

    for root, dirs, files in os.walk(copy_dir):
        for file in files:
            if file.endswith('.h'):
                with open(fs.join(root, file), 'r') as f:
                    text = f.read()
                text = text.replace('#include', '//')
                with open(fs.join(root, file), 'w') as f:
                    f.write(text)

    generator = c_generator.CGenerator()
    types_and_structs = generator.visit(ast)

    with open(header_name, 'w') as tmp:
        tmp.write(types_and_structs + header_text)

    return header_name


def search_for_lib(directory):
    lib_name = ''
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.startswith('lib') and file.endswith('.a'):
                return root, file


def generate_module(directory):
    if fs.isdir(directory):
        # handle strings ends with '/'
        if directory[-1] == '/':
            directory = directory[:-1]

        dirname = fs.basename(directory)
    else:
        sys.exit('Please give an existing directory.')

    output_dir = fs.join(path.TOOLS_ROOT, 'generator_output')

    if not fs.isdir(output_dir):
        os.mkdir(output_dir)

    output_dir = fs.join(output_dir, dirname + '_module')

    if not fs.isdir(output_dir):
        os.mkdir(output_dir)

    copy_dir = fs.join(output_dir, dirname)
    fs.copytree(directory, copy_dir)
    tmp_file = fs.join(output_dir, 'tmp.h')
    header_to_parse = create_header_to_parse(tmp_file, copy_dir)
    lib_root, lib_name = search_for_lib(directory)

    header_file = gen_header(directory)
    c_file = gen_c_source(header_to_parse, dirname)
    json_file = MODULES_JSON.format(NAME=dirname)
    cmake_file = MODULE_CMAKE.format(NAME=dirname, LIBRARY=lib_name[3:-2])

    with open(fs.join(output_dir, dirname + '_js_wrapper.h'), 'w') as h:
        h.write(header_file)

    with open(fs.join(output_dir, dirname + '_js_wrapper.c'), 'w') as c:
        c.write(c_file)

    with open(fs.join(output_dir, 'modules.json'), 'w') as json:
        json.write(json_file)

    with open(fs.join(output_dir, 'module.cmake'), 'w') as cmake:
        cmake.write(cmake_file)

    fs.copyfile(fs.join(lib_root, lib_name), fs.join(output_dir, lib_name))

    fs.rmtree(copy_dir)
    fs.remove(tmp_file)

    return output_dir, dirname + '_module'

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('directory',
                        help='Root directory of c api headers.')

    args = parser.parse_args()

    generate_module(args.directory)
