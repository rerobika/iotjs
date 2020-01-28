#!/usr/bin/env python

# Copyright 2019-present Samsung Electronics Co., Ltd. and other contributors
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

class DefinitonGenerator(object):
    DEF_KIND_FUNCTION = 0
    DEF_KIND_CONST = 1
    DEF_KIND_LET = 2
    DEF_KIND_VAR = 3
    DEF_KIND_INTERFACE = 4

    def_kind_desc_strings = [
        'function',
        'const',
        'let',
        'var',
        'interface'
    ]

    def __init__(self, file_name, lib_name):
        self.file = open(file_name, 'w') if file_name else None
        if self.file:
            self.file.write('export as namespace ' + lib_name + ';\n\n')

    def line_writer(self, def_kind, line):
        if self.file:
            self.file.write('export ' + self.def_kind_desc_strings[def_kind] + ' ' + line)

    def append_defintion(self, def_kind, name, desc, ret_type=''):
        return self.line_writer(def_kind, name + desc + ret_type + ';\n')

    def append_interface(self, name, body):
        self.line_writer(self.DEF_KIND_INTERFACE, name + ' {\n'+ '\n'.join(body) + '\n}\n')

    def macro_to_type(self, macro):
        if macro.is_char() or macro.is_string():
            return 'string'
        elif macro.is_number():
            return 'number'

        return 'any'

    def to_anonymous_func_def(self, desc, ret_type):
        return desc + ' => ' + ret_type

    def node_to_type(self, node_type):
        if node_type.is_void():
            return 'void'

        if node_type.is_char():
            return 'string'
        elif node_type.is_number() or node_type.is_enum():
            return 'number'
        elif node_type.is_record():
            return 'object'
        elif node_type.is_function():
            return 'function'
        elif node_type.is_pointer():
            if node_type.get_pointee_type().is_char():
               return 'string'
            elif node_type.get_pointee_type().is_number():
                return 'Uint8Array'
            elif node_type.get_pointee_type().is_function():
                return 'function'
            elif node_type.get_pointee_type().is_record():
                return 'object'
        return 'any'

    def append_type(self, js_type):
        return ': ' + js_type

    def append_named_node_type(self, name, node_type):
        return name + self.append_node_type(node_type) + ';'

    def append_node_type(self, node_type):
        return self.append_type(self.node_to_type(node_type))

    def append_macro_type(self, macro):
        return self.append_type(self.macro_to_type(macro))

    def to_record_name(self, ns_name):
        return ns_name.split(' ')[-1]

    def to_record_definition(self, name, desc, is_interface_def=True):
        return ('\t' if is_interface_def else '') + name + ': ' + desc + (';' if is_interface_def else '')

    def emit_record(self, record):
        body = []

        for member in record.field_decls:
            if member.type.is_record():
                inner_record = member.type.get_as_record_decl()
                body.append(self.to_record_definition(member.name, self.to_record_name(inner_record.ns_name)))
            elif member.type.is_pointer() and member.type.get_pointee_type().is_function():
                func = member.get_as_function()
                body.append(self.to_record_definition(member.name, self.emit_ext_function(func, True)))
            else:
                body.append('\t' + self.append_named_node_type(member.name, member.type))

        self.append_interface(record.name, body)

    def emit_number_array(self, num_array):
        self.append_defintion(self.DEF_KIND_CONST, num_array.name, self.append_type('Array<number>'))

    def emit_global_record(self, name, record):
        self.append_defintion(self.DEF_KIND_VAR, name, self.append_type(self.to_record_name(record)))

    def emit_global_const_record(self, name, record):
        self.append_defintion(self.DEF_KIND_CONST, name, self.append_type(self.to_record_name(record)))

    def emit_enum(self, enum):
        self.append_defintion(self.DEF_KIND_CONST, enum, self.append_type('number'))

    def emit_macro(self, macro):
        self.append_defintion(self.DEF_KIND_CONST, macro.name, self.append_macro_type(macro))

    def emit_const_variable(self, cost_var):
        self.append_defintion(self.DEF_KIND_CONST, cost_var.name, self.append_node_type(cost_var.type))

    def emit_global_variable(self, var):
        self.append_defintion(self.DEF_KIND_VAR, var.name, self.append_node_type(var.type))

    def emit_ext_function(self, function, anonymous=False):
        params = function.params
        desc = []

        for _, param in enumerate(params):
            if param.type.is_record():
                record = param.type.get_as_record_decl()
                desc.append(self.to_record_definition(param.name, self.to_record_name(record.ns_name), False))
            elif param.type.is_pointer() and param.type.get_pointee_type().is_function():
                desc.append(param.name + ': ' + self.emit_ext_function(param.get_as_function(), True))
            else:
                desc.append(param.name + self.append_node_type(param.type))

        params = '(' + ', '.join(desc) + ')'
        ret_type = self.append_node_type(function.return_type)

        if anonymous:
            return self.to_anonymous_func_def (params, self.node_to_type(function.return_type))

        return self.append_defintion(self.DEF_KIND_FUNCTION, function.name, params, ret_type)

    def __del__(self):
        if self.file:
            self.file.close()

