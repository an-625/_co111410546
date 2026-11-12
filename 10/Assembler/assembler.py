#!/usr/bin/env python3
"""Nand2Tetris Hack 組譯器 (assembler)。

用法:
    python assembler.py Program.asm          # 產生 Program.hack
    python assembler.py Program.asm -o X.hack

支援 Hack 組語:
    A-instruction: @value / @symbol
    C-instruction: dest=comp;jump (dest、jump 可省略)
    L-instruction: (LABEL)
    註解與空白行會被忽略。
"""

import sys
from pathlib import Path

# ---------- 指令翻譯表 ----------

COMP_TABLE = {
    "0":   "0101010",
    "1":   "0111111",
    "-1":  "0111010",
    "D":   "0001100",
    "A":   "0110000",
    "!D":  "0001101",
    "!A":  "0110001",
    "-D":  "0001111",
    "-A":  "0110011",
    "D+1": "0011111",
    "A+1": "0110111",
    "D-1": "0001110",
    "A-1": "0110010",
    "D+A": "0000010",
    "D-A": "0010011",
    "A-D": "0000111",
    "D&A": "0000000",
    "D|A": "0010101",
    "M":   "1110000",
    "!M":  "1110001",
    "-M":  "1110011",
    "M+1": "1110111",
    "M-1": "1110010",
    "D+M": "1000010",
    "D-M": "1010011",
    "M-D": "1000111",
    "D&M": "1000000",
    "D|M": "1010101",
}

DEST_TABLE = {
    None: "000",
    "M":  "001",
    "D":  "010",
    "MD": "011",
    "A":  "100",
    "AM": "101",
    "AD": "110",
    "AMD": "111",
}

JUMP_TABLE = {
    None: "000",
    "JGT": "001",
    "JEQ": "010",
    "JGE": "011",
    "JLT": "100",
    "JNE": "101",
    "JLE": "110",
    "JMP": "111",
}

PREDEFINED_SYMBOLS = {
    "R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5,
    "R6": 6, "R7": 7, "R8": 8, "R9": 9, "R10": 10, "R11": 11,
    "R12": 12, "R13": 13, "R14": 14, "R15": 15,
    "SP": 0, "LCL": 1, "ARG": 2, "THIS": 3, "THAT": 4,
    "SCREEN": 16384, "KBD": 24576,
}

VAR_START = 16


def clean_line(line):
    """去掉註解與前後空白；回傳 None 表示空行。"""
    code = line.split("//", 1)[0].strip()
    return code if code else None


class SymbolTable:
    def __init__(self):
        self.symbols = dict(PREDEFINED_SYMBOLS)
        self.next_var = VAR_START

    def add_label(self, label, address):
        if label in self.symbols:
            raise ValueError(f"符號重複定義: {label}")
        self.symbols[label] = address

    def get(self, label):
        if label not in self.symbols:
            self.symbols[label] = self.next_var
            self.next_var += 1
        return self.symbols[label]


def parse_c(code):
    """把 C 指令拆成 (dest, comp, jump)。"""
    dest, jump = None, None
    if "=" in code:
        dest, code = code.split("=", 1)
    if ";" in code:
        code, jump = code.split(";", 1)
    comp = code
    if dest is not None and dest.strip() not in DEST_TABLE:
        raise ValueError(f"無效的 dest: {dest}")
    if comp.strip() not in COMP_TABLE:
        raise ValueError(f"無效的 comp: {comp}")
    if jump is not None and jump.strip() not in JUMP_TABLE:
        raise ValueError(f"無效的 jump: {jump}")
    return dest and dest.strip(), comp.strip(), jump and jump.strip()


def first_pass(lines):
    """掃出所有 (L-instruction, 符號)，並記錄指令位址。"""
    table = SymbolTable()
    instructions = []
    address = 0
    for lineno, raw in enumerate(lines, 1):
        code = clean_line(raw)
        if code is None:
            continue
        if code.startswith("(") and code.endswith(")"):
            table.add_label(code[1:-1].strip(), address)
        else:
            instructions.append((lineno, code))
            address += 1
    return table, instructions


def translate_a(code, table):
    symbol = code[1:].strip()
    if symbol.isdigit():
        value = int(symbol)
    else:
        value = table.get(symbol)
    if not 0 <= value <= 32767:
        raise ValueError(f"A 指令位址超出範圍: {symbol}")
    return format(value, "016b")


def translate_c(code):
    dest, comp, jump = parse_c(code)
    bits = "111" + COMP_TABLE[comp] + DEST_TABLE[dest] + JUMP_TABLE[jump]
    return bits


def assemble(lines):
    table, instructions = first_pass(lines)
    out = []
    for lineno, code in instructions:
        try:
            if code.startswith("@"):
                bits = translate_a(code, table)
            else:
                bits = translate_c(code)
        except ValueError as e:
            raise ValueError(f"第 {lineno} 行: {e}") from None
        out.append(bits)
    return out


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
    if dst is None:
        dst = src.with_suffix(".hack")

    with open(src, encoding="utf-8") as f:
        lines = f.readlines()

    try:
        result = assemble(lines)
    except ValueError as e:
        print(f"組譯錯誤: {e}", file=sys.stderr)
        return 1

    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        for bits in result:
            f.write(bits + "\n")
    print(f"已輸出 {dst} ({len(result)} 行指令)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
