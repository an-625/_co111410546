#!/usr/bin/env python3
"""Nand2Tetris VM 翻譯器 (VM translator)。

用法:
    python vm_translator.py Prog.vm           # 產生 Prog.asm
    python vm_translator.py 資料夾             # 翻譯資料夾內所有 .vm，產生 資料夾/資料夾.asm
    python vm_translator.py Prog.vm -o X.asm  # 指定輸出檔

支援完整 VM 語言 (專案 7 + 8):
    算術:   add sub neg eq gt lt and or not
    記憶體: push/pop constant|local|argument|this|that|temp|pointer|static
    流程:   label goto if-goto
    函式:   function call return
    輸入為資料夾時，自動加入 bootstrap 程式碼呼叫 Sys.init。
"""

import sys
from pathlib import Path

SEGMENT_POINTERS = {
    "local": "LCL",
    "argument": "ARG",
    "this": "THIS",
    "that": "THAT",
}

ARITHMETIC_OPS = {"add", "sub", "neg", "eq", "gt", "lt", "and", "or", "not"}

COMPARISON_JUMPS = {"eq": "JEQ", "gt": "JGT", "lt": "JLT"}


class VMTranslator:
    def __init__(self):
        self.output = []
        self.uid = 0
        self.current_function = None
        self.current_file = None

    # ---------- 基礎工具 ----------

    def emit(self, *lines):
        self.output.extend(lines)

    def new_label(self, prefix):
        self.uid += 1
        return f"VM${prefix}.{self.uid}"

    def scoped_label(self, label):
        if self.current_function:
            return f"{self.current_function}${label}"
        return label

    def _push_d(self):
        self.emit(
            "@SP",
            "A=M",
            "M=D",
            "@SP",
            "M=M+1",
        )

    # ---------- 主流程 ----------

    def translate_file(self, path):
        self.current_file = path.stem
        self.current_function = None
        text = path.read_text(encoding="utf-8")
        for lineno, raw in enumerate(text.splitlines(), 1):
            code = raw.split("//", 1)[0].strip()
            if not code:
                continue
            try:
                self.translate_line(code)
            except ValueError as e:
                raise ValueError(f"{path.name}:{lineno}: {e}") from None

    def translate_line(self, code):
        parts = code.split()
        op = parts[0]

        if op in ARITHMETIC_OPS:
            self._expect(parts, 1, op)
            self.translate_arithmetic(op)
        elif op == "push":
            self.translate_push(parts)
        elif op == "pop":
            self.translate_pop(parts)
        elif op == "label":
            self._expect(parts, 2, op)
            self.emit(f"// label {parts[1]}", f"({self.scoped_label(parts[1])})")
        elif op == "goto":
            self._expect(parts, 2, op)
            self.emit(f"// goto {parts[1]}", f"@{self.scoped_label(parts[1])}", "0;JMP")
        elif op == "if-goto":
            self._expect(parts, 2, op)
            self.emit(
                f"// if-goto {parts[1]}",
                "@SP",
                "AM=M-1",
                "D=M",
                f"@{self.scoped_label(parts[1])}",
                "D;JNE",
            )
        elif op == "function":
            self.translate_function(parts)
        elif op == "call":
            self.translate_call(parts)
        elif op == "return":
            self._expect(parts, 1, op)
            self.translate_return()
        else:
            raise ValueError(f"未知的 VM 指令: {op}")

    @staticmethod
    def _expect(parts, count, op):
        if len(parts) != count:
            raise ValueError(f"指令 {op} 的參數數量錯誤: {parts}")
        return parts

    # ---------- 算術與邏輯 ----------

    def translate_arithmetic(self, op):
        self.emit(f"// {op}")
        if op in ("add", "sub", "and", "or"):
            comp = {"add": "D+M", "sub": "M-D", "and": "D&M", "or": "D|M"}[op]
            self.emit(
                "@SP",
                "AM=M-1",
                "D=M",
                "A=A-1",
                f"M={comp}",
            )
        elif op == "neg":
            self.emit("@SP", "A=M-1", "M=-M")
        elif op == "not":
            self.emit("@SP", "A=M-1", "M=!M")
        else:
            jump = COMPARISON_JUMPS[op]
            true_label = self.new_label("TRUE")
            end_label = self.new_label("END")
            self.emit(
                "@SP",
                "AM=M-1",
                "D=M",
                "A=A-1",
                "D=M-D",
                f"@{true_label}",
                f"D;{jump}",
                "@SP",
                "A=M-1",
                "M=0",
                f"@{end_label}",
                "0;JMP",
                f"({true_label})",
                "@SP",
                "A=M-1",
                "M=-1",
                f"({end_label})",
            )

    # ---------- 記憶體存取 ----------

    def translate_push(self, parts):
        self._expect(parts, 3, "push")
        kind, index_text = parts[1], parts[2]
        index = self._parse_index(index_text, kind)
        self.emit(f"// push {kind} {index}")

        if kind == "constant":
            self.emit(f"@{index}", "D=A")
            self._push_d()
        elif kind in SEGMENT_POINTERS:
            self.emit(
                f"@{index}",
                "D=A",
                f"@{SEGMENT_POINTERS[kind]}",
                "A=D+M",
                "D=M",
            )
            self._push_d()
        elif kind == "temp":
            self.emit(f"@{5 + index}", "D=M")
            self._push_d()
        elif kind == "pointer":
            self.emit("@" + ("THIS" if index == 0 else "THAT"), "D=M")
            self._push_d()
        elif kind == "static":
            self.emit(f"@{self.current_file}.{index}", "D=M")
            self._push_d()
        else:
            raise ValueError(f"未知的記憶體區段: {kind}")

    def translate_pop(self, parts):
        self._expect(parts, 3, "pop")
        kind, index_text = parts[1], parts[2]
        if kind == "constant":
            raise ValueError("pop constant 不合法")
        index = self._parse_index(index_text, kind)
        self.emit(f"// pop {kind} {index}")

        if kind in SEGMENT_POINTERS:
            self.emit(
                f"@{index}",
                "D=A",
                f"@{SEGMENT_POINTERS[kind]}",
                "D=D+M",
                "@R13",
                "M=D",
            )
            self._pop_to("@R13", indirect=True)
        elif kind == "temp":
            self._pop_to(f"@{5 + index}")
        elif kind == "pointer":
            self._pop_to("@" + ("THIS" if index == 0 else "THAT"))
        elif kind == "static":
            self._pop_to(f"@{self.current_file}.{index}")
        else:
            raise ValueError(f"未知的記憶體區段: {kind}")

    def _pop_to(self, target, indirect=False):
        self.emit(
            "@SP",
            "AM=M-1",
            "D=M",
            target,
        )
        if indirect:
            self.emit("A=M")
        self.emit("M=D")

    @staticmethod
    def _parse_index(text, kind):
        try:
            index = int(text)
        except ValueError:
            raise ValueError(f"{kind} 的索引不是數字: {text}") from None
        if index < 0:
            raise ValueError(f"{kind} 的索引不可為負: {index}")
        if kind == "pointer" and index not in (0, 1):
            raise ValueError(f"pointer 索引只能是 0 或 1: {index}")
        return index

    # ---------- 函式呼叫 ----------

    def translate_function(self, parts):
        self._expect(parts, 3, "function")
        name, locals_text = parts[1], parts[2]
        try:
            local_count = int(locals_text)
        except ValueError:
            raise ValueError(f"function 的區域變數數量不是數字: {locals_text}") from None
        if local_count < 0:
            raise ValueError(f"function 的區域變數數量不可為負: {local_count}")

        self.current_function = name
        self.emit(f"// function {name} {local_count}", f"({name})")
        if local_count:
            self.emit("@SP", "A=M")
            for _ in range(local_count):
                self.emit("M=0", "A=A+1")
            self.emit("D=A", "@SP", "M=D")

    def translate_call(self, parts):
        self._expect(parts, 3, "call")
        name, args_text = parts[1], parts[2]
        try:
            arg_count = int(args_text)
        except ValueError:
            raise ValueError(f"call 的參數數量不是數字: {args_text}") from None
        if arg_count < 0:
            raise ValueError(f"call 的參數數量不可為負: {arg_count}")

        return_label = self.new_label("RET")
        self.emit(f"// call {name} {arg_count}", f"@{return_label}", "D=A")
        self._push_d()

        for register in ("LCL", "ARG", "THIS", "THAT"):
            self.emit(f"@{register}", "D=M")
            self._push_d()

        self.emit(
            "@SP",
            "D=M",
            "@5",
            "D=D-A",
            f"@{arg_count}",
            "D=D-A",
            "@ARG",
            "M=D",
            "@SP",
            "D=M",
            "@LCL",
            "M=D",
            f"@{name}",
            "0;JMP",
            f"({return_label})",
        )

    def translate_return(self):
        self.emit(
            "// return",
            "@LCL",
            "D=M",
            "@R13",
            "M=D",
            "@5",
            "A=D-A",
            "D=M",
            "@R14",
            "M=D",
            "@SP",
            "AM=M-1",
            "D=M",
            "@ARG",
            "A=M",
            "M=D",
            "@ARG",
            "D=M+1",
            "@SP",
            "M=D",
        )
        for register in ("THAT", "THIS", "ARG", "LCL"):
            self.emit("@R13", "AM=M-1", "D=M", f"@{register}", "M=D")
        self.emit("@R14", "A=M", "0;JMP")

    # ---------- Bootstrap ----------

    def write_bootstrap(self):
        self.emit(
            "// bootstrap: SP = 256, call Sys.init 0",
            "@256",
            "D=A",
            "@SP",
            "M=D",
        )
        self.translate_call(["call", "Sys.init", "0"])
        end_label = self.new_label("BOOT")
        self.emit(f"({end_label})", f"@{end_label}", "0;JMP")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1

    src = Path(argv[1])
    dst = None
    if "-o" in argv:
        i = argv.index("-o")
        if i + 1 < len(argv):
            dst = Path(argv[i + 1])

    translator = VMTranslator()
    try:
        if src.is_dir():
            vm_files = sorted(src.glob("*.vm"))
            if not vm_files:
                print(f"錯誤: {src} 裡沒有 .vm 檔", file=sys.stderr)
                return 1
            if dst is None:
                dst = src / (src.name + ".asm")
            translator.write_bootstrap()
            for vm_file in vm_files:
                translator.translate_file(vm_file)
        else:
            if not src.exists():
                print(f"錯誤: 找不到 {src}", file=sys.stderr)
                return 1
            if dst is None:
                dst = src.with_suffix(".asm")
            translator.translate_file(src)
    except ValueError as e:
        print(f"翻譯錯誤: {e}", file=sys.stderr)
        return 1

    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        for line in translator.output:
            f.write(line + "\n")
    print(f"已輸出 {dst} ({len(translator.output)} 行組語)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
