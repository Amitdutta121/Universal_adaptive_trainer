/* Lesson seeds per Python subtopic: the idea, a worked example and a predict question.
 * Every *_out / predict_ans was computed by running the code (scratchpad/lessons_src.py).
 * TODO(real): generated per subtopic from the book section by the lesson generator. */
window.LESSON_SEEDS = {
 "Integers and floats": {
  "idea": "Whole numbers are ints; numbers with a decimal point are floats. Dividing with / always gives a float.",
  "example": "print(7 / 2)\nprint(7 // 2)\nprint(type(7 / 2))",
  "example_out": "3.5\n3\n<class 'float'>",
  "predict": "x = 10 / 5\nprint(x)",
  "predict_q": "What does this print?",
  "predict_ans": "2.0"
 },
 "Strings as values": {
  "idea": "Text in quotes is a string. + joins strings; * repeats them.",
  "example": "greeting = 'hi'\nprint(greeting + '!' * 3)",
  "example_out": "hi!!!",
  "predict": "print('ab' * 2 + 'c')",
  "predict_q": "What does this print?",
  "predict_ans": "ababc"
 },
 "Type conversion": {
  "idea": "int(), float() and str() turn one type into another. input() always gives a string.",
  "example": "age = '19'\nprint(int(age) + 1)\nprint(age + '1')",
  "example_out": "20\n191",
  "predict": "print(str(3) + str(4))",
  "predict_q": "What does this print?",
  "predict_ans": "34"
 },
 "Booleans": {
  "idea": "True and False are values of type bool. Comparisons produce them.",
  "example": "print(3 > 2)\nprint(type(3 > 2))",
  "example_out": "True\n<class 'bool'>",
  "predict": "print(5 == 5.0)",
  "predict_q": "What does this print?",
  "predict_ans": "True"
 },
 "Assignment": {
  "idea": "= gives a name to a value. The right side is worked out first, then stored in the name.",
  "example": "price = 4\nprice = price + 1\nprint(price)",
  "example_out": "5",
  "predict": "a = 2\nb = a\na = 7\nprint(b)",
  "predict_q": "What does this print?",
  "predict_ans": "2"
 },
 "Operator precedence": {
  "idea": "* and / happen before + and -. Use parentheses when you mean something else.",
  "example": "print(2 + 3 * 4)\nprint((2 + 3) * 4)",
  "example_out": "14\n20",
  "predict": "print(10 - 2 * 3)",
  "predict_q": "What does this print?",
  "predict_ans": "4"
 },
 "Augmented assignment": {
  "idea": "x += 1 is short for x = x + 1. The same works for -=, *= and /=.",
  "example": "score = 10\nscore += 5\nscore *= 2\nprint(score)",
  "example_out": "30",
  "predict": "n = 3\nn -= 1\nn *= 4\nprint(n)",
  "predict_q": "What does this print?",
  "predict_ans": "8"
 },
 "Naming rules": {
  "idea": "Names can use letters, digits and _, can't start with a digit, and are case-sensitive.",
  "example": "total = 1\nTotal = 2\nprint(total, Total)",
  "example_out": "1 2",
  "predict": "item_count = 3\nprint(item_count * 2)",
  "predict_q": "What does this print?",
  "predict_ans": "6"
 },
 "if / elif / else": {
  "idea": "Python checks each condition from the top and runs only the first branch that is true.",
  "example": "temp = 18\nif temp > 25:\n    print('hot')\nelif temp > 15:\n    print('mild')\nelse:\n    print('cold')",
  "example_out": "mild",
  "predict": "x = 30\nif x > 10:\n    print('A')\nelif x > 20:\n    print('B')",
  "predict_q": "What does this print?",
  "predict_ans": "A"
 },
 "Comparison operators": {
  "idea": "==, !=, <, >, <= and >= compare two values and give True or False. = is assignment, not comparison.",
  "example": "print(4 != 4)\nprint('apple' < 'banana')",
  "example_out": "False\nTrue",
  "predict": "print(3 <= 3, 3 < 3)",
  "predict_q": "What does this print?",
  "predict_ans": "True False"
 },
 "Logical operators": {
  "idea": "and is True only if both sides are; or is True if either is; not flips a value.",
  "example": "age = 20\nprint(age > 18 and age < 65)",
  "example_out": "True",
  "predict": "print(not (2 > 1) or 3 > 4)",
  "predict_q": "What does this print?",
  "predict_ans": "False"
 },
 "Nested conditionals": {
  "idea": "An if inside another if only runs when the outer condition is true.",
  "example": "logged_in = True\nadmin = False\nif logged_in:\n    if admin:\n        print('admin page')\n    else:\n        print('home page')",
  "example_out": "home page",
  "predict": "a, b = 5, 2\nif a > 3:\n    if b > 3:\n        print('both')\n    else:\n        print('only a')",
  "predict_q": "What does this print?",
  "predict_ans": "only a"
 },
 "while loops": {
  "idea": "A while loop repeats while its condition is true. Something in the body must change so it can stop.",
  "example": "n = 3\nwhile n > 0:\n    print(n)\n    n -= 1",
  "example_out": "3\n2\n1",
  "predict": "i = 1\nwhile i < 10:\n    i *= 2\nprint(i)",
  "predict_q": "What does this print?",
  "predict_ans": "16"
 },
 "range() and counted loops": {
  "idea": "range(start, stop, step) counts from start up to, but not including, stop.",
  "example": "for i in range(2, 8, 2):\n    print(i, end=' ')",
  "example_out": "2 4 6 ",
  "predict": "for i in range(3):\n    print(i * 2, end=' ')",
  "predict_q": "What does this print?",
  "predict_ans": "0 2 4 "
 },
 "break and continue": {
  "idea": "break leaves the loop now; continue skips to the next round.",
  "example": "for n in range(1, 6):\n    if n == 2:\n        continue\n    if n == 4:\n        break\n    print(n)",
  "example_out": "1\n3",
  "predict": "for c in 'code':\n    if c == 'd':\n        break\n    print(c, end='')",
  "predict_q": "What does this print?",
  "predict_ans": "co"
 },
 "Loop accumulators": {
  "idea": "Start a variable before the loop, update it inside, use it after.",
  "example": "total = 0\nfor n in [3, 5, 2]:\n    total += n\nprint(total)",
  "example_out": "10",
  "predict": "count = 0\nfor w in ['a', 'bb', 'ccc']:\n    if len(w) > 1:\n        count += 1\nprint(count)",
  "predict_q": "What does this print?",
  "predict_ans": "2"
 },
 "Defining functions": {
  "idea": "def names a block of code you can run again by calling it. The body runs only when called.",
  "example": "def greet(name):\n    print('Hi', name)\n\ngreet('Ana')\ngreet('Bo')",
  "example_out": "Hi Ana\nHi Bo",
  "predict": "def show():\n    print('in')\nprint('out')",
  "predict_q": "What does this print?",
  "predict_ans": "out"
 },
 "Parameters and arguments": {
  "idea": "Parameters are the names in def; arguments are the values you pass when calling. They match by position.",
  "example": "def area(w, h):\n    return w * h\n\nprint(area(3, 4))",
  "example_out": "12",
  "predict": "def f(a, b):\n    return a - b\nprint(f(2, 5))",
  "predict_q": "What does this print?",
  "predict_ans": "-3"
 },
 "Return values": {
  "idea": "return sends a value back to the caller. A function with no return gives back None.",
  "example": "def double(x):\n    return x * 2\n\nprint(double(4) + 1)",
  "example_out": "9",
  "predict": "def f(x):\n    x * 2\nprint(f(3))",
  "predict_q": "What does this print?",
  "predict_ans": "None"
 },
 "Scope": {
  "idea": "Names created inside a function are local: they disappear when it ends and don't change outside names.",
  "example": "x = 10\ndef f():\n    x = 5\n    print(x)\nf()\nprint(x)",
  "example_out": "5\n10",
  "predict": "count = 1\ndef bump():\n    count = 2\nbump()\nprint(count)",
  "predict_q": "What does this print?",
  "predict_ans": "1"
 },
 "String indexing": {
  "idea": "s[0] is the first character; s[-1] is the last. Indexing past the end is an error.",
  "example": "word = 'python'\nprint(word[0], word[-1])",
  "example_out": "p n",
  "predict": "print('hello'[1])",
  "predict_q": "What does this print?",
  "predict_ans": "e"
 },
 "Slicing": {
  "idea": "s[start:stop] takes characters from start up to, but not including, stop.",
  "example": "word = 'python'\nprint(word[1:4])\nprint(word[:2])\nprint(word[-3:])",
  "example_out": "yth\npy\nhon",
  "predict": "print('abcdef'[2:5])",
  "predict_q": "What does this print?",
  "predict_ans": "cde"
 },
 "String methods": {
  "idea": "Methods like .upper(), .strip() and .replace() return a new string; the original doesn't change.",
  "example": "name = '  Ada '\nclean = name.strip().upper()\nprint(clean)\nprint(name)",
  "example_out": "ADA\n  Ada ",
  "predict": "s = 'cat'\ns.upper()\nprint(s)",
  "predict_q": "What does this print?",
  "predict_ans": "cat"
 },
 "f-strings": {
  "idea": "An f-string puts values into text with {}. You can format numbers inside the braces.",
  "example": "item, price = 'tea', 2.5\nprint(f'{item} costs ${price:.2f}')",
  "example_out": "tea costs $2.50",
  "predict": "n = 3\nprint(f'{n} x {n} = {n * n}')",
  "predict_q": "What does this print?",
  "predict_ans": "3 x 3 = 9"
 },
 "List indexing": {
  "idea": "Lists are numbered from 0. You can change an item by assigning to its index.",
  "example": "nums = [4, 8, 15]\nnums[1] = 9\nprint(nums)",
  "example_out": "[4, 9, 15]",
  "predict": "xs = ['a', 'b', 'c']\nprint(xs[-2])",
  "predict_q": "What does this print?",
  "predict_ans": "b"
 },
 "List methods": {
  "idea": ".append() adds one item to the end; .pop() removes and returns the last one. Both change the list in place.",
  "example": "stack = [1, 2]\nstack.append(3)\ntop = stack.pop()\nprint(top, stack)",
  "example_out": "3 [1, 2]",
  "predict": "xs = [3, 1, 2]\nxs.sort()\nprint(xs)",
  "predict_q": "What does this print?",
  "predict_ans": "[1, 2, 3]"
 },
 "Aliasing": {
  "idea": "b = a does not copy a list; it gives the same list a second name. A change through either name shows through both.",
  "example": "a = [1, 2, 3]\nb = a\nb[0] = 42\nprint(a)",
  "example_out": "[42, 2, 3]",
  "predict": "x = [1, 2]\ny = x\ny.append(3)\nprint(x)",
  "predict_q": "What does this print?",
  "predict_ans": "[1, 2, 3]"
 },
 "List comprehensions": {
  "idea": "[expr for item in items if condition] builds a new list in one line.",
  "example": "nums = [1, 2, 3, 4]\nprint([n * n for n in nums if n % 2 == 0])",
  "example_out": "[4, 16]",
  "predict": "print([c.upper() for c in 'abc'])",
  "predict_q": "What does this print?",
  "predict_ans": "['A', 'B', 'C']"
 },
 "Keys and values": {
  "idea": "A dict maps keys to values. Keys must be unchangeable (hashable): strings, numbers and tuples work; lists don't.",
  "example": "ages = {'ana': 19, 'bo': 21}\nages['cy'] = 20\nprint(ages['bo'], len(ages))",
  "example_out": "21 3",
  "predict": "d = {(1, 2): 'point'}\nprint(d[(1, 2)])",
  "predict_q": "What does this print?",
  "predict_ans": "point"
 },
 "Iterating a dict": {
  "idea": "Looping over a dict gives its keys. Use .items() to get key and value together.",
  "example": "stock = {'apple': 3, 'pear': 0}\nfor fruit, n in stock.items():\n    print(fruit, n)",
  "example_out": "apple 3\npear 0",
  "predict": "d = {'a': 1, 'b': 2}\nfor k in d:\n    print(k, end='')",
  "predict_q": "What does this print?",
  "predict_ans": "ab"
 },
 "Counting with dicts": {
  "idea": "To count, look up the old count with .get(key, 0) and add one.",
  "example": "counts = {}\nfor w in ['hi', 'yo', 'hi']:\n    counts[w] = counts.get(w, 0) + 1\nprint(counts)",
  "example_out": "{'hi': 2, 'yo': 1}",
  "predict": "c = {}\nfor ch in 'aab':\n    c[ch] = c.get(ch, 0) + 1\nprint(c['a'])",
  "predict_q": "What does this print?",
  "predict_ans": "2"
 },
 "Nested dicts": {
  "idea": "A value in a dict can itself be a dict. Chain the keys to reach inside.",
  "example": "users = {'ana': {'age': 19, 'city': 'Reno'}}\nprint(users['ana']['city'])",
  "example_out": "Reno",
  "predict": "d = {'x': {'y': 5}}\nprint(d['x']['y'] + 1)",
  "predict_q": "What does this print?",
  "predict_ans": "6"
 },
 "Tuple packing": {
  "idea": "a, b = 1, 2 packs and unpacks in one step. It also swaps: a, b = b, a.",
  "example": "a, b = 1, 2\na, b = b, a\nprint(a, b)",
  "example_out": "2 1",
  "predict": "x, y, z = 'abc'\nprint(y)",
  "predict_q": "What does this print?",
  "predict_ans": "b"
 },
 "Immutability": {
  "idea": "Tuples and strings can't be changed after they're made; build a new one instead.",
  "example": "point = (2, 3)\nmoved = (point[0] + 1, point[1])\nprint(point, moved)",
  "example_out": "(2, 3) (3, 3)",
  "predict": "t = (1, 2)\nt = t + (3,)\nprint(t)",
  "predict_q": "What does this print?",
  "predict_ans": "(1, 2, 3)"
 },
 "Set operations": {
  "idea": "A set keeps one copy of each item. | joins sets, & keeps what's in both, - removes.",
  "example": "a = {1, 2, 3}\nb = {2, 3, 4}\nprint(a & b, a - b)",
  "example_out": "{2, 3} {1}",
  "predict": "print(len({1, 1, 2, 2, 3}))",
  "predict_q": "What does this print?",
  "predict_ans": "3"
 },
 "Choosing a collection": {
  "idea": "List for order and repeats, tuple for fixed records, set for uniqueness, dict for lookups by key.",
  "example": "tags = ['py', 'web', 'py']\nprint(len(tags), len(set(tags)))",
  "example_out": "3 2",
  "predict": "print(sorted(set('banana')))",
  "predict_q": "What does this print?",
  "predict_ans": "['a', 'b', 'n']"
 },
 "Reading files": {
  "idea": "open(path) gives a file; looping over it gives one line at a time, each ending in a newline.",
  "example": "lines = ['a\\n', 'b\\n']  # what a file of two lines gives\nfor line in lines:\n    print(line.strip())",
  "example_out": "a\nb",
  "predict": "line = 'ok\\n'\nprint(len(line), len(line.strip()))",
  "predict_q": "What does this print?",
  "predict_ans": "3 2"
 },
 "Writing files": {
  "idea": "Mode 'w' replaces the file; 'a' adds to the end. write() doesn't add a newline for you.",
  "example": "parts = []\nparts.append('one')\nparts.append('two\\n')\nprint(repr(''.join(parts)))",
  "example_out": "'onetwo\\n'",
  "predict": "print(repr('x' + '\\n'))",
  "predict_q": "What does this print?",
  "predict_ans": "'x\\n'"
 },
 "with statements": {
  "idea": "with open(...) as f closes the file for you when the block ends, even after an error.",
  "example": "class F:\n    def __enter__(self):\n        print('open')\n        return self\n    def __exit__(self, *e):\n        print('closed')\nwith F():\n    print('reading')",
  "example_out": "open\nreading\nclosed",
  "predict": "class F:\n    def __enter__(self):\n        return self\n    def __exit__(self, *e):\n        print('bye')\nwith F():\n    print('hi')",
  "predict_q": "What does this print?",
  "predict_ans": "hi\nbye"
 },
 "Parsing lines": {
  "idea": "split() breaks a line into parts; convert each part to the type you need.",
  "example": "line = 'ana,19,Reno'\nname, age, city = line.split(',')\nprint(name, int(age) + 1)",
  "example_out": "ana 20",
  "predict": "print('3 4 5'.split()[1])",
  "predict_q": "What does this print?",
  "predict_ans": "4"
 },
 "try / except": {
  "idea": "Code in try runs; if it raises an error, the matching except block runs instead of crashing.",
  "example": "try:\n    n = int('abc')\nexcept ValueError:\n    n = 0\nprint(n)",
  "example_out": "0",
  "predict": "try:\n    print(1 / 0)\nexcept ZeroDivisionError:\n    print('nope')",
  "predict_q": "What does this print?",
  "predict_ans": "nope"
 },
 "Raising errors": {
  "idea": "raise stops the function and reports a problem the caller can catch.",
  "example": "def check(age):\n    if age < 0:\n        raise ValueError('negative')\n    return age\ntry:\n    check(-1)\nexcept ValueError as e:\n    print('error:', e)",
  "example_out": "error: negative",
  "predict": "def f():\n    raise KeyError('k')\ntry:\n    f()\nexcept KeyError:\n    print('caught')",
  "predict_q": "What does this print?",
  "predict_ans": "caught"
 },
 "Common error types": {
  "idea": "NameError: unknown name. TypeError: wrong type for the operation. IndexError: index out of range. KeyError: missing key.",
  "example": "for bad in ['[1][5]', \"'a' + 1\"]:\n    try:\n        eval(bad)\n    except Exception as e:\n        print(type(e).__name__)",
  "example_out": "IndexError\nTypeError",
  "predict": "try:\n    {}['x']\nexcept Exception as e:\n    print(type(e).__name__)",
  "predict_q": "What does this print?",
  "predict_ans": "KeyError"
 },
 "finally": {
  "idea": "finally runs after try (and except), whether or not there was an error.",
  "example": "try:\n    print('try')\nfinally:\n    print('done')",
  "example_out": "try\ndone",
  "predict": "try:\n    x = 1 / 0\nexcept ZeroDivisionError:\n    print('a')\nfinally:\n    print('b')",
  "predict_q": "What does this print?",
  "predict_ans": "a\nb"
 },
 "Defining a class": {
  "idea": "A class is a blueprint; calling it makes an object (an instance).",
  "example": "class Dog:\n    pass\nd = Dog()\nprint(type(d).__name__)",
  "example_out": "Dog",
  "predict": "class A:\n    pass\nprint(A() is A())",
  "predict_q": "What does this print?",
  "predict_ans": "False"
 },
 "Attributes": {
  "idea": "Attributes are names stored on an object: obj.name. Each object has its own.",
  "example": "class Pet:\n    pass\np, q = Pet(), Pet()\np.name = 'Rex'\nq.name = 'Ivy'\nprint(p.name, q.name)",
  "example_out": "Rex Ivy",
  "predict": "class C:\n    pass\nc = C()\nc.x = 3\nc.x += 1\nprint(c.x)",
  "predict_q": "What does this print?",
  "predict_ans": "4"
 },
 "Methods": {
  "idea": "A method is a function inside a class. Python passes the object in as self.",
  "example": "class Counter:\n    def __init__(self):\n        self.n = 0\n    def tick(self):\n        self.n += 1\nc = Counter()\nc.tick(); c.tick()\nprint(c.n)",
  "example_out": "2",
  "predict": "class S:\n    def hi(self):\n        return 'hi'\nprint(S().hi().upper())",
  "predict_q": "What does this print?",
  "predict_ans": "HI"
 },
 "__init__": {
  "idea": "__init__ runs when an object is made and sets up its attributes.",
  "example": "class Point:\n    def __init__(self, x, y):\n        self.x, self.y = x, y\np = Point(2, 5)\nprint(p.x + p.y)",
  "example_out": "7",
  "predict": "class B:\n    def __init__(self):\n        print('made')\nb = B()\nb2 = B()",
  "predict_q": "What does this print?",
  "predict_ans": "made\nmade"
 }
};
