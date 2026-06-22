with open('frontend/src/app/execution/page.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

stack = []
for idx, line in enumerate(lines):
    line_num = idx + 1
    for char_idx, char in enumerate(line):
        if char in '{(':
            stack.append((char, line_num, char_idx))
        elif char in '})':
            if not stack:
                print(f"Extra closing {char} on line {line_num}:{char_idx}")
                continue
            top_char, top_line, top_col = stack.pop()
            if (char == '}' and top_char != '{') or (char == ')' and top_char != '('):
                print(f"Mismatch: {top_char} from {top_line}:{top_col} closed by {char} on {line_num}:{char_idx}")

print("Brace nesting remaining on stack at end of file:")
for item in stack:
    print(f"Unclosed {item[0]} on line {item[1]}:{item[2]}")
