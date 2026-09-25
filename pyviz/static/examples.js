// Example programs shown in the "Example" dropdown.
window.EXAMPLES = [
  {
    name: "Recursion: factorial",
    code: `def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(4)
print("4! =", result)
`,
  },
  {
    name: "Lists & aliasing",
    code: `a = [1, 2, 3]
b = a          # b refers to the SAME list
c = list(a)    # c is a copy
b.append(4)
c.append(99)
print(a, b, c)
matrix = [[0] * 2 for _ in range(2)]
matrix[0][1] = 5
`,
  },
  {
    name: "Bubble sort",
    code: `def bubble_sort(items):
    n = len(items)
    for i in range(n):
        for j in range(n - i - 1):
            if items[j] > items[j + 1]:
                items[j], items[j + 1] = items[j + 1], items[j]
    return items

data = [5, 2, 4, 1]
bubble_sort(data)
print(data)
`,
  },
  {
    name: "Classes: linked list",
    code: `class Node:
    def __init__(self, value, next=None):
        self.value = value
        self.next = next

head = None
for v in [3, 2, 1]:
    head = Node(v, head)

node = head
total = 0
while node:
    total += node.value
    node = node.next
print("sum:", total)
`,
  },
  {
    name: "Dictionaries: word count",
    code: `text = "the cat and the hat"
counts = {}
for word in text.split():
    counts[word] = counts.get(word, 0) + 1
best = max(counts, key=counts.get)
print(best, counts[best])
`,
  },
  {
    name: "Closures",
    code: `def make_counter():
    count = 0
    def increment():
        nonlocal count
        count += 1
        return count
    return increment

counter = make_counter()
counter()
counter()
print(counter())
`,
  },
  {
    name: "Fibonacci (tree recursion)",
    code: `def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

print(fib(4))
`,
  },
  {
    name: "Generators",
    code: `def squares(limit):
    for i in range(limit):
        yield i * i

total = 0
for sq in squares(4):
    total += sq
print(total)
`,
  },
  {
    name: "Exceptions",
    code: `def safe_divide(a, b):
    try:
        return a / b
    except ZeroDivisionError as err:
        print("oops:", err)
        return None

x = safe_divide(10, 2)
y = safe_divide(1, 0)
z = int("not a number")   # uncaught!
`,
  },
  {
    name: "Reading input()",
    code: `name = input("Your name? ")
age = int(input("Your age? "))
print(f"Hi {name}, next year you'll be {age + 1}")
`,
    stdin: "Ada\n36",
  },
];
