---
title: 数据结构与算法 · 05 · LeetCode HOT 100 in Python（后50）
date: 2026-03-02 11:38:24
tags:
- 数据结构与算法
published: true
hideInList: false
feature: null
isTop: false
chapters_per_page: 1
---
回溯、二分查找、栈、堆、贪心、动态规划、多维动态规划、技巧。

<!-- more -->

专题10 回溯
专题11 二分查找
专题12 栈
专题13 堆
专题14 贪心
专题15 动态规划
专题16 多维动态规划
专题17 技巧

### 专题10 回溯

46 全排列

回溯模板：结束条件，遍历选择，做出选择。

<div class="algoviz" data-module="lc46-全排列" data-title="46 全排列 · 步骤可视化"></div>
```
class Solution:
    def permute(self, nums: List[int]) -> List[List[int]]:
        res = []

        # 回溯: 结束, 遍历, 选择
        def backtrack(path, used):
            if len(path) == len(nums):
                res.append(path[:])
            for i in range(len(nums)):
                if used[i]:
                    continue

                path.append(nums[i])
                used[i] = True
                backtrack(path, used)
                path.pop()
                used[i] = False

        backtrack([], [False] * len(nums))
        return res
```

78 子集

回溯需要考虑当前start时可以做哪些选择。

<div class="algoviz" data-module="lc78-子集" data-title="78 子集 · 步骤可视化"></div>
```
class Solution:
    def subsets(self, nums: List[int]) -> List[List[int]]:
        res = []
        def backtrack(start, path):
            res.append(path[:])
            for i in range(start, len(nums)):
                path.append(nums[i])
                backtrack(i + 1, path)
                path.pop()

        backtrack(0, [])
        return res
```

17 电话号码的字母组合

回溯需要考虑当前位置可以做出哪些选择。

<div class="algoviz" data-module="lc17-电话号码的字母组合" data-title="17 电话号码的字母组合 · 步骤可视化"></div>
```
class Solution:
    def letterCombinations(self, digits: str) -> List[str]:
        adict = {'2': 'abc', '3': 'def', '4': 'ghi', '5': 'jkl', '6': 'mno', '7': 'pqrs', '8': 'tuv', '9': 'wxyz'}
        res = []

        def backtrack(path, cur):
            if cur == len(digits):
                res.append(''.join(path[:]))
                return
            for choice in adict[digits[cur]]:
                path.append(choice)
                backtrack(path, cur + 1)
                path.pop()

        backtrack([], 0)
        return res
```

39 组合总和

（集合中元素可以重复使用，不同位置元素不同）

重复使用通过传入相同的i实现。

<div class="algoviz" data-module="lc39-组合总和" data-title="39 组合总和 · 步骤可视化"></div>
```
class Solution:
    def combinationSum(self, candidates: List[int], target: int) -> List[List[int]]:
        res = []

        def backtrack(path, cur, start):
            if cur == 0:
                res.append(path[:])
                return

            for i in range(start, len(candidates)):
                if candidates[i] > cur:
                    continue
                path.append(candidates[i])
                backtrack(path, cur - candidates[i], i) # 细节: 可以重复使用, 所以是i
                path.pop()

        candidates.sort() # 排序优化剪枝
        backtrack([], target, 0)
        return res
```

变式：组合总和II

（集合中每个元素只能重复使用一次，不同位置可能有相同元素）

关键：只能使用一次通过传入i+1实现，不同位置可能有相同元素通过排序后连续元素剪枝实现。

<div class="algoviz" data-module="lc39-组合总和-v2" data-title="39 组合总和 · 步骤可视化"></div>
```
class Solution:
    def combinationSum2(self, candidates: List[int], target: int) -> List[List[int]]:
        res = []
        def backtrack(path, start, remaining):
            if remaining == 0:
                res.append(path[:])
                return

            for i in range(start, len(candidates)):
                if candidates[i] > remaining: # 剪枝
                    return
                if i > start and candidates[i] == candidates[i - 1]:
                    continue
                path.append(candidates[i])
                backtrack(path, i + 1, remaining - candidates[i]) # 细节: i + 1
                path.pop()

        candidates.sort()
        backtrack([], 0, target)
        return res
```

22 括号生成

回溯选择：如果左括号数量不到n，则可以加左括号；如果右括号数量少于左括号（当然也不到n），则可以加右括号。

<div class="algoviz" data-module="lc22-括号生成" data-title="22 括号生成 · 步骤可视化"></div>
```
class Solution:
    def generateParenthesis(self, n: int) -> List[str]:
        res = []

        def backtrack(path, left, right):
            if len(path) == 2 * n:
                res.append(''.join(path))
            # 可以加左括号的条件
            if left < n:
                path.append('(')
                backtrack(path, left + 1, right)
                path.pop()

            # 可以加右括号的条件: 右括号数量小于左括号数量
            if right < left:
                path.append(')')
                backtrack(path, left, right + 1)
                path.pop()

        backtrack([], 0, 0)
        return res
```



[79. 单词搜索](https://leetcode.cn/problems/word-search/)

对于单词搜索问题，我们需要以整个棋盘的每个点为起点，搜索所有可能的路径（如DFS）。

为了剪枝不可行的路径（下述好几处提前返回都起到剪枝的作用），我们需要维护 `visited` 数组。我们利用相应位置的特殊字符来变相维护 `visited` 数组。但是，**由于节点需要重复使用，我们需要“回溯”：在标记 `visited` 之前保存原状态，用完之后恢复原状态。**

这道题最有趣的是考虑复杂度。

- 时间复杂度：$O(m \times n \times 3^L)$ ，其中 $m$ 和 $n$ 是二维网格 `board` 的行数和列数，$L$ 是 `word` 的长度。这是因为，我们需要以每个点为起点，而在搜索过程中由于剪枝，来的方向一定此时已经被标记为 `#` 了，所以实际上只有3个方向可选。这是一个很宽松的上界。
- 空间复杂度：$O(L)$ ，因为我们省去了额外开 `visited` 数组，但是递归栈的深度取决于 `word` 的长度。

```python
class Solution:
    def exist(self, board: List[List[str]], word: str) -> bool:
        DIR = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        m, n = len(board), len(board[0])
        
        def dfs(x, y, cur):
            if board[x][y] != word[cur]:
                return False
            if cur == len(word) - 1:
                return True
            tmp = board[x][y]                     # 这三行是visited数组的逻辑
            board[x][y] = '#'                     # 最重要!
            for dx, dy in DIR:
                nx, ny = x + dx, y + dy
                if 0 <= nx < m and 0 <= ny < n:
                    if dfs(nx, ny, cur + 1):
                        return True
            board[x][y] = tmp                     # 一定要记得回溯 (前保存, 后恢复) 哦
            return False
        
        for i in range(m):
            for j in range(n):
                if dfs(i, j, 0):
                    return True
        return False
```



131 分割回文串

<div class="algoviz" data-module="lc131-分割回文串" data-title="131 分割回文串 · 步骤可视化"></div>
```
class Solution:
    def partition(self, s: str) -> List[List[str]]:
        res = []
        def backtrack(start, path):
            if start == len(s):
                res.append(path[:])

            for end in range(start, len(s)):
                subs = s[start:end + 1]
                if subs[::-1] == subs:
                    path.append(subs)
                    backtrack(end + 1, path)
                    path.pop()
        backtrack(0, [])
        return res
```

51 N皇后

仍然是回溯的结束条件、遍历选择空间、做出选择的三步走。

对于N皇后问题，为了简化，我们用回溯函数代表处理特定行（此时排除掉了各行重复的问题），然后对于该函数，遍历所有列作为可能的选择，通过cols、diag1和diag2三个集合作为排除选择的条件。

N皇后的行条件自动保证，列条件有n个（通过col是否存在确定），主对角线有2n-1个（row - col的取值范围是从-(n-1)到(n-1)），副对角线有2n-1个（row + col的取值范围是从2到2n）。通过set是否存在即可。

<div class="algoviz" data-module="lc51-n皇后" data-title="51 N皇后 · 步骤可视化"></div>
```
class Solution:
    def solveNQueens(self, n: int) -> List[List[str]]:
        res = []
        board = [['.'] * n for _ in range(n)]
        cols = set()
        diag1 = set()
        diag2 = set()

        def backtrack(row):
            if row == n:
                res.append([''.join(board_row) for board_row in board])
                return
            for col in range(n):
                if col in cols or (row - col) in diag1 or (row + col) in diag2:
                    continue
                # 做选择
                board[row][col] = 'Q'
                cols.add(col)
                diag1.add(row - col)
                diag2.add(row + col)
                backtrack(row + 1)
                board[row][col] = '.'
                cols.remove(col)
                diag1.remove(row - col)
                diag2.remove(row + col)

        backtrack(0)
        return res
```

239 滑动窗口最大值

发现之前有一道滑动窗口的题忘了做了。

首先挨个元素推入最大堆。在最大堆中元素足够多时，将不在窗口的全部pop出来，则剩下的就是在窗口内、且值最大的元素。

堆通过heapq包对heap数组进行处理，两个方法分别叫做heapq.heappush和heapq.heappop。

<div class="algoviz" data-module="lc239-滑动窗口最大值" data-title="239 滑动窗口最大值 · 步骤可视化"></div>
```
class Solution:
    def maxSlidingWindow(self, nums: List[int], k: int) -> List[int]:
        # 最大堆, 所以存储 (-num, i)
        # 堆顶是heap[0]
        heap = []
        result = []
        for i, num in enumerate(nums):
            heapq.heappush(heap, (-num, i))
            if i >= k - 1:
                # 已存入长度为k的元素
                # 窗口应该是 [i - k + 1, i] 这k个元素
                while heap and heap[0][1] <= i - k:
                    heapq.heappop(heap)
                result.append(-heap[0][0])
        return result
```

更好的做法是维护一个单调队列：

**目标是：队头始终是窗口内的最大元素。**

每次加入新元素前，将队尾小于新元素的全部移除。（不可能成为最大值）

加入后、添加res前，将队头不在窗口内的全部移除。

（单调队列一般就是这种移除队尾的小元素的写法用法，然后因为这里有窗口的要求、还需要移除队头不在窗口内的元素。）

<div class="algoviz" data-module="lc239-滑动窗口最大值-v2" data-title="239 滑动窗口最大值 · 步骤可视化"></div>
```
class Solution:
    def maxSlidingWindow(self, nums: List[int], k: int) -> List[int]:
        # 维护单调队列
        # 每次都首先移除队尾比它小的元素, 然后再加入, 这样就会使得队列始终是单调递减的
        q = deque()
        res = []
        for i, num in enumerate(nums):
            # 移除队尾比num小的元素
            while q and q[-1][1] < num:
                q.pop()
            q.append((i, num))
            # 移除队头不在窗口内的元素
            while q and q[0][0] <= i - k:
                q.popleft()

            if i >= k - 1:
                res.append(q[0][1])
        return res
```

### 专题11 二分查找

> 二分有一个令人头疼的问题叫做边界条件。这里一次性讲清楚。
>
> 如果要找的元素一定在区间里，可以使用**闭区间**： `left = 0` ，`right = n - 1` ，循环条件是 `left <= right` 。
>
> 如果要找的元素可能不存在，可以使用**左闭右开区间**：`left = 0` ，`right = n` ，循环条件是 `left < right` 。
>
> ~~左闭右开的写法比较符合 [Dijkstra的论述](https://www.cs.utexas.edu/~EWD/transcriptions/EWD08xx/EWD831.html)，但是~~ 左闭右闭的写法会强迫你思考哪些元素被取到和排除。

| 写法         | 搜索区间        | 循环条件        | left 更新        | right 更新        | 返回值        | 典型场景   |
| :----------- | :-------------- | :-------------- | :--------------- | :---------------- | :------------ | :--------- |
| **左闭右闭** | `[left, right]` | `left <= right` | `left = mid + 1` | `right = mid - 1` | `mid` 或 `-1` | 找确切值   |
| **左闭右开** | `[left, right)` | `left < right`  | `left = mid + 1` | `right = mid`     | `left`        | 找插入位置 |



35 搜索插入位置

bisect的两个函数分别叫bisect_left和bisect_right。

它们的特点是，你把新元素插入到它返回的位置，数组仍然保持有序。

如果元素已存在，则left返回已存在元素的第一个位置，right返回已存在元素的最后一个位置的下一个位置。

<div class="algoviz" data-module="lc35-搜索插入位置" data-title="35 搜索插入位置 · 步骤可视化"></div>
```
class Solution:
    def searchInsert(self, nums: List[int], target: int) -> int:
        return bisect.bisect_left(nums, target)
```

74 搜索二维矩阵

用二分查找的话就是对每行搜索一下。

需要注意的是，很有可能返回的下标为n（未找到，且待寻找元素比该行都要大），所以顺手加个条件。

<div class="algoviz" data-module="lc74-搜索二维矩阵" data-title="74 搜索二维矩阵 · 步骤可视化"></div>
```
class Solution:
    def searchMatrix(self, matrix: List[List[int]], target: int) -> bool:
        m, n = len(matrix), len(matrix[0])
        for i in range(m):
            j = bisect.bisect_left(matrix[i], target)
            if j < n and matrix[i][j] == target:
                return True
        return False
```



[34. 在排序数组中查找元素的第一个和最后一个位置](https://leetcode.cn/problems/find-first-and-last-position-of-element-in-sorted-array/)

我特别喜欢下面这个板子，因为它把找上、下界的方式用**闭区间的二分查找**写得特别清楚，完全不容易写错。

> 闭区间的二分查找的最好板子：
>
> 利用 `pos` 数组记录返回值。所有更新都使用 `mid - 1` 和 `mid + 1` 。
>
> ps. `left` 和 `right` 初始化构成的**范围是有含义的**。这道题我们是要在下标 `0` 到 `n-1` 范围内搜索。如果以后搜索的是个数，可能就是最少个数和最多个数了。一定要仔细想清楚这里的范围，不要闭着眼睛乱写。

时间复杂度：$O(\log n)$ ，空间复杂度：$O(1)$

<div class="algoviz" data-module="lc74-搜索二维矩阵-v2" data-title="74 搜索二维矩阵 · 步骤可视化"></div>
```python
class Solution:
    def searchRange(self, nums: List[int], target: int) -> List[int]:
        def find_boundary(is_left: bool):
            left, right = 0, len(nums) - 1
            pos = -1 # 精华
            while left <= right:
                mid = (left + right) // 2
                if nums[mid] == target:
                    pos = mid # 精华
                    if is_left:
                        right = mid - 1
                    else:
                        left = mid + 1
                elif nums[mid] < target:
                    left = mid + 1
                else:
                    right = mid - 1
            return pos
        return [find_boundary(True), find_boundary(False)]
```



[33. 搜索旋转排序数组](https://leetcode.cn/problems/search-in-rotated-sorted-array/)

这是一道二分的变式，关键在于首先找到有序的那一半区间，然后判断看 `target` 是否在有序的这一半区间。否则就在另一半。

**我们只敢在有序区间上用 `nums[left] <= target < nums[mid]` 这种条件判断！**

然后关于各种边界条件怎么记忆：

- 优先判断 `nums[mid] == target` ，之后 `mid` 一定会从区间里排除，所以对应地给 `target` 条件里面用到 `nums[mid]` 的**都写成小于号**，而另外半边使用小于等于。
- 我使用了我最喜欢的左闭右闭写法，所以到处都很干净。我喜欢这个板子。

时间复杂度：$O(\log n)$ ，空间复杂度：$O(1)$

```python
class Solution:
    def search(self, nums: List[int], target: int) -> int:
        left, right = 0, len(nums) - 1
        while left <= right:
            mid = (left + right) // 2
            if nums[mid] == target:
                return mid
            if nums[left] <= nums[mid]: # 为了能用有序区间的条件判断, 我们需要先确定有序区间
                if nums[left] <= target < nums[mid]:  # mid已排除
                    right = mid - 1                   # mid已排除
                else:
                    left = mid + 1                    # mid已排除
            else:
                if nums[mid] < target <= nums[right]: # mid已排除
                    left = mid + 1                    # mid已排除
                else:
                    right = mid - 1                   # mid已排除
        return -1
```



153 寻找旋转排序数组中的最小值

还是一样的道理，旋转排序数组通过判断哪半段区间是有序的，来解决问题。另外那一半无序的区间只需要通过移动端点逼近处理即可。

<div class="algoviz" data-module="lc153-寻找旋转排序数组中的最小值" data-title="153 寻找旋转排序数组中的最小值 · 步骤可视化"></div>
```
class Solution:
    def findMin(self, nums: List[int]) -> int:
        l, r = 0, len(nums) - 1
        minVal = nums[0]
        while l <= r:
            mid = (l + r) // 2
            if nums[mid] < minVal:
                minVal = min(minVal, nums[mid])
            else:
                if nums[l] <= nums[mid]:
                    # 有序
                    minVal = min(minVal, nums[l])
                    l = mid + 1
                else:
                    minVal = min(minVal, nums[mid + 1])
                    r = mid - 1
        return minVal
```



[4. 寻找两个正序数组的中位数](https://leetcode.cn/problems/median-of-two-sorted-arrays/)

找到给两个数组切开的位置，使得切痕左边的两段数组整体值，小于等于切痕右边整体值。并且，这两个整体大小基本相同。

实际是左边整体比右边整体多0个（偶数）或1个（奇数）元素，所以用了 `(m + n + 1) // 2` 这样的上取整写法。

这个板子真难背啊。为了让它好背一点，一定要理解最关键的三行：

- `i = (left + right) // 2` ，意味着**数组 `nums1` 左边一段有 `i` 个元素**
- `j = total_left - i` ，意味着数组 `nums2` 左边一段有 `j` 个元素
- `left, right = 0, m` ，意味着数组 `nums1` 左边一段**可以有 `0` 到 `m` 个元素**（注意绝对不能写成 `0` 到 `m-1` ！）

其余所有代码都是服务于这三行的。

当然，还有中位数的返回方式：如果是奇数个，左边两段多出的那一个最大元素就是中位数；如果是偶数个，左边两段的最大元素和右边两段的最小元素的均值就是中位数。

时间复杂度：$O(\log (\min \{m, n\}))$ ，空间复杂度：$O(1)$

```python
class Solution:
    def findMedianSortedArrays(self, nums1: List[int], nums2: List[int]) -> float:
        if len(nums1) > len(nums2):
            nums1, nums2 = nums2, nums1
        m, n = len(nums1), len(nums2)
        total_left = (m + n + 1) // 2 # 左半比右半多一个元素

        left, right = 0, m # 关键!
        # 这里的i搜索的是"分割点左边的数量"而不是"下标", 所以不是闭着眼睛用0, m-1初始化, 而是0, m才正确!
        while left <= right:
            i = (left + right) // 2  # 两行最关键的代码
            j = total_left - i
            nums1_left_max = float('-inf') if i == 0 else nums1[i - 1]
            nums1_right_min = float('inf') if i == m else nums1[i]
            nums2_left_max = float('-inf') if j == 0 else nums2[j - 1]
            nums2_right_min = float('inf') if j == n else nums2[j]
            if nums1_left_max <= nums2_right_min and nums2_left_max <= nums1_right_min:
                if (m + n) % 2 == 1:
                    return max(nums1_left_max, nums2_left_max)
                else:
                    return (max(nums1_left_max, nums2_left_max) + min(nums1_right_min, nums2_right_min)) / 2.0
            elif nums1_left_max > nums2_right_min:
                right = i - 1
            else:
                left = i + 1
        return -1
```

### 专题12 栈

[20. 有效的括号](https://leetcode.cn/problems/valid-parentheses/)

这道题单纯括号匹配本身是容易想到的（栈），在此基础上要记得奇数时的剪枝、以及栈的判空。

> 为了把对应关系写得好写一些，我们往往使用正排/倒排的哈希表。

时间复杂度为 $O(n)$ ，空间复杂度为 $O(n+|\Sigma|)$ ，其中 $|\Sigma|$ 是词汇表个数（如本题的 $|\Sigma|=6$ ）。

```python
class Solution:
    def isValid(self, s: str) -> bool:
        if len(s) % 2 == 1:
            return False
        stk = []
        pair = {
            '(': ')',
            '[': ']',
            '{': '}'
        }
        for ch in s:
            if ch in pair:
                stk.append(ch)
            else:
                if stk and pair[stk[-1]] == ch:
                    stk.pop()
                else:
                    return False
        return not stk
```

155 最小栈

如果要有额外的功能，则添加额外的数据结构。

<div class="algoviz" data-module="lc155-最小栈" data-title="155 最小栈 · 步骤可视化"></div>
```
class MinStack:

    def __init__(self):
        # 两个结构各自实现栈和最小
        self.stk = []
        self.minStk = []

    def push(self, val: int) -> None:
        self.stk.append(val)
        i = bisect.bisect_left(self.minStk, val)
        self.minStk.insert(i, val)

    def pop(self) -> None:
        val = self.stk.pop()
        i = bisect.bisect_left(self.minStk, val)
        self.minStk.pop(i)

    def top(self) -> int:
        return self.stk[-1]

    def getMin(self) -> int:
        return self.minStk[0]


        # Your MinStack object will be instantiated and called as such:
        # obj = MinStack()
        # obj.push(val)
        # obj.pop()
        # param_3 = obj.top()
# param_4 = obj.getMin()
```

394 字符串解码

首先不考虑递归的情况即可。考虑最简单的例子：

`3[a]2[b]`

对于字符串解码，它肯定是从左往右读的。

(1) 读到数字时构造当前数字这个简单，

(2) 读到字符时构造当前字符串。

需要稍微仔细考虑一下的是读到 `[` 和 `]` 的情况。

(3) 假如说前面已经解码出了 `aaa`，在读到 `[` 时，应该把 `aaa`存入栈中，作为等待连接起来的前置字符串，然后就可以开始构造 `[]` 里面的字符串了。

(4) 在读到 `]` 时，展开当前一段的全部所需信息已经满足，只要把前置字符串取出，然后展开即可。

再考虑递归的情况：

每当读到 `]` 时，就可以把栈中存的前面某一段给拼进来。

<div class="algoviz" data-module="lc394-字符串解码" data-title="394 字符串解码 · 步骤可视化"></div>
```
class Solution:
    def decodeString(self, s: str) -> str:
        numStk = []
        strStk = []
        curNum = 0
        curStr = ''

        for c in s:
            if c.isdigit():
                curNum = 10 * curNum + int(c)
            elif c == '[':
                # 构造完毕, 当前数字和字符串入栈
                numStk.append(curNum)
                strStk.append(curStr) # 临时存放, 便于一会取出作为prevStr
                curNum = 0
                curStr = ''
            elif c == ']':
                repeat_times = numStk.pop()
                prevStr = strStk.pop()
                curStr = prevStr + curStr * repeat_times
            else:
                curStr += c

        return curStr
```

739 每日温度

当当前温度高于栈顶的一系列温度时，取出它们的下标，将相应下标位置置为下标差。

<div class="algoviz" data-module="lc739-每日温度" data-title="739 每日温度 · 步骤可视化"></div>
```
class Solution:
    def dailyTemperatures(self, temperatures: List[int]) -> List[int]:
        stk = []
        res = [0] * len(temperatures)
        for i, temp in enumerate(temperatures):
            while stk and stk[-1][1] < temp:
                cur_i, _ = stk.pop()
                res[cur_i] = i - cur_i
            stk.append((i, temp))
        return res
```

[84. 柱状图中最大的矩形](https://leetcode.cn/problems/largest-rectangle-in-histogram/)

这个单调栈问题如果有一些直观直觉，会好把握一点。

![](posts/migrated/post-images/20260302113916.png)

直觉：我们考虑以当前柱子为高度的矩形，则它最多可以延伸到左右两边第一个低于它的柱子。

这两个柱子确定了最大宽度，当前柱子确定高度。

其他高度的矩形，当前柱子不关心。

故使用一个单调递增栈，当遇到一个比栈顶更矮的柱子时，就意味着找到了**栈顶柱子**的右边界，可以立刻弹出并计算以其为高度的最大矩形。（此时栈顶和两侧矮柱子形成“**低高低**”关系，可以立即结算这个高柱子）

为了解决边界问题，我们往两侧添加高度为0的“柱子”。

> 这道题与[42. 接雨水](https://leetcode.cn/problems/trapping-rain-water/)十分相似，二者可以说是有对偶关系：一个处理低高低这样“凸”的形状，一个处理高低高这样“凹”的形状。使用单调栈的解法，时空复杂度均为$O(n)$。
>
> 对于低高低（这道题），矩形宽度取决于两侧第一个低于当前矩形的高度，所以维护单调递增栈，栈顶即对应“当前矩形”。
>
> 对于高低高（接雨水），雨水量取决于两侧第一个高于当前高度的更低者，所以维护单调递减栈，栈顶即对应“当前凹槽”。（虽然这个单调栈解法不是最优、空间复杂度不如双指针，但考虑到对称性，值得提一下）
>
> （更深刻地，它们结构特别像、所以都可以用单调栈。但是接雨水中的“最小者”这个关系可以传递，所以还可以用双指针；而柱状图中最大的矩形的“最近者”这个关系对应的宽度信息不可以传递，所以不可以用双指针）

时间复杂度：$O(n)$，空间复杂度：$O(n)$

（相比起来，暴力寻找两边第一个小于当前高度的解法，时间复杂度为$O(n^2)$，空间复杂度为$O(1)$）

```python
class Solution:
    def largestRectangleArea(self, heights: List[int]) -> int:
        heights = [0] + heights + [0]
        stk = [] # 存储索引, 单调递增栈
        max_area = 0
        for i, h in enumerate(heights):
            # 结算栈顶高度, 并且同一个h有可能连续结算好多个!
            while stk and heights[stk[-1]] > h: # 关键: 我们找到的是**栈顶高度**的**两侧矮于它的高度**!
                height = heights[stk.pop()]
                width = i - stk[-1] - 1
                max_area = max(max_area, height * width)
            stk.append(i)
        return max_area
```

[85. 最大矩形](https://leetcode.cn/problems/maximal-rectangle/)

这道题可以化归为[84. 柱状图中最大的矩形](https://leetcode.cn/problems/largest-rectangle-in-histogram/)。关键是，我们如果以每一行为底，则它及上面的部分恰好构成一个“柱状图”。

这个柱状图的巧妙之处在于，如果底当前列的元素为1，则高度是递推过来的；如果为0，则断开，高度为0。

~~写一遍权当复习84了，默写着默写着发现自己84的 `while` 循环没想到，谢谢85~~

时间复杂度：$O(mn)$，空间复杂度：$O(n)$

```python
class Solution:
    def maximalRectangle(self, matrix: List[List[str]]) -> int:
        if not matrix or not matrix[0]:
            return 0
        m, n = len(matrix), len(matrix[0])
        heights = [0] * n
        max_area = 0
        for i in range(m):
            # 重要: 对当前行进行条形图统计时, 如果遇到0, 则"断开"
            for j in range(n):
                if matrix[i][j] == '1':
                    heights[j] += 1
                else:
                    heights[j] = 0
            max_area = max(max_area, self.largestRectangleArea(heights))
        return max_area
    
    def largestRectangleArea(self, heights):
        heights = [0] + heights + [0]
        stk = []
        max_area = 0
        for i, h in enumerate(heights):
            while stk and heights[stk[-1]] > h:
                height = heights[stk.pop()]
                width = i - stk[-1] - 1
                max_area = max(max_area, height * width)
            stk.append(i)
        return max_area
```

### 专题13 堆

[253 会议室 II](https://neetcode.io/problems/meeting-schedule-ii/question)

十分经典的会议安排问题，这次问你至少需要多少个会议室。

它需要先把会议**按照开始时间排序**（$O(n \log n)$），然后建立一个结束时间的**小根堆**（`heapq` 默认是小根堆，如果需要大根堆则存负值、使用时再取负即可）：

遍历会议，**如果开始时间不早于结束最早的会议室，则可以复用该会议室**（从堆中删除，然后把新结束时间加入堆中）。每次堆操作是 $O(\log n)$ 的，总计 $n$ 次操作。

时间复杂度：$O(n \log n)$ ，空间复杂度：$O(n)$ 。

>  [安排最少的会议室](https://leetcode.cn/problems/meeting-rooms-ii/description/) 按照开始时间排序，[安排最多的会议室](https://leetcode.cn/problems/non-overlapping-intervals/) 按照结束时间排序。

```python
"""
Definition of Interval:
class Interval(object):
    def __init__(self, start, end):
        self.start = start
        self.end = end
"""

class Solution:
    def minMeetingRooms(self, intervals: List[Interval]) -> int:
        if not intervals:
            return 0
        intervals.sort(key=lambda x: x.start)
        heap = [intervals[0].end] # heap存当前正在进行的会议的end
        for i in range(1, len(intervals)):
            if intervals[i].start >= heap[0]:
                heapq.heappop(heap)
            heapq.heappush(heap, intervals[i].end)
        return len(heap)
```



215 数组中的第K个最大元素

解法一：**最小堆**

维护大小保持为 $k$ 个的最小堆，如果长度超出时把**最小元素**逐出，从而最后在堆中留下的就是前K个最大元素，其中最小的就是堆顶。

时间复杂度：$O(n \log k)$，空间复杂度：$O(k)$

<div class="algoviz" data-module="lc215-数组中的第k个最大元素" data-title="215 数组中的第K个最大元素 · 步骤可视化"></div>
```python
class Solution:
    def findKthLargest(self, nums: List[int], k: int) -> int:
        heap = [] # 最小堆解法
        for num in nums:
            heapq.heappush(heap, num)
            if len(heap) > k:
                heapq.heappop(heap)
        return heap[0]
```

解法二：**最大堆**

对全部元素建堆（$O(n)$），然后 `pop` $k$ 次（$O(k \log n)$）。

时间复杂度：$O(n + k \log n)$，空间复杂度：$O(n)$

<div class="algoviz" data-module="lc215-数组中的第k个最大元素-v2" data-title="215 数组中的第K个最大元素 · 步骤可视化"></div>
```
class Solution:
    def findKthLargest(self, nums: List[int], k: int) -> int:
        nums = [-x for x in nums]
        heapq.heapify(nums)
        for i in range(k - 1):
            heapq.heappop(nums)
        return -heapq.heappop(nums)
```

347 前K个高频元素

第一种方法当然是按照频率降序排序，然后取前k个。

说起来以前对key的理解不够时不太能理解lambda函数。自从意识到key是任意的单参数函数、返回一个可比较的值之后，就很明确了。

```
class Solution:
    def topKFrequent(self, nums: List[int], k: int) -> List[int]:
        freq = defaultdict(int)
        for num in nums:
            freq[num] += 1
        items = list(sorted(freq.items(), key = lambda x: -x[1]))
        return [x[0] for x in items[:k]]
```

当然也可以拿堆去做。

<div class="algoviz" data-module="lc347-前k个高频元素-v2" data-title="347 前K个高频元素 · 步骤可视化"></div>
```
class Solution:
    def topKFrequent(self, nums: List[int], k: int) -> List[int]:
        freq = defaultdict(int)
        for num in nums:
            freq[num] += 1
        items = [(-f, v) for v, f in freq.items()]
        heapq.heapify(items)
        res = []
        for i in range(k):
            res.append(heapq.heappop(items)[1])
        return res
```

295 数据流的中位数

方法是维护一个最大堆和一个最小堆，各一半大小，使得最大堆始终小于等于最小堆。则根据它们的堆顶即可计算得到中位数。

注意由于python的heapq引起的语法麻烦：最大堆里面存放的是负值。

```
class MedianFinder:

    def __init__(self):
        self.small = [] # 最大堆, 存较小的元素, 存的都是负值
        self.large = [] # 最小堆, 存较大的元素, 存的都是正值

    def addNum(self, num: int) -> None:
        # 始终使得最大堆小于等于最小堆
        heapq.heappush(self.small, -num)
        if self.small and self.large and -self.small[0] > self.large[0]:
            val = -heapq.heappop(self.small)
            heapq.heappush(self.large, val)

        # 最大堆比最小堆多至多一个元素
        if len(self.small) > len(self.large) + 1:
            val = -heapq.heappop(self.small)
            heapq.heappush(self.large, val)
        elif len(self.large) > len(self.small):
            val = -heapq.heappop(self.large)
            heapq.heappush(self.small, val)

    def findMedian(self) -> float:
        if (len(self.small) + len(self.large)) % 2:
            return -self.small[0]
        else:
            return (-self.small[0] + self.large[0]) / 2


            # Your MedianFinder object will be instantiated and called as such:
            # obj = MedianFinder()
            # obj.addNum(num)
# param_2 = obj.findMedian()
```

### 专题14 贪心

虽然同样称为贪心，但是这一套贪心的四道题和算法导论的四道题细究起来并不是一类。

算法导论的贪心一般是“做显式的贪心选择”，通过替换/交换法进行贪心论证。例如活动选择问题，每次都选择结束时间最早的相容活动，这样的话可以给其他活动留出最多的时间、以整体选择最多的活动。

而这里的四道题更倾向于“迭代维护状态，以做出最优选择”。

第一道需要在某个价格时买入（但并不知道什么时候买入）、在当前价格时卖出，所以维护历史最低价格；

第二道需要知道最远能到达哪里，所以边遍历边维护；

第三道需要跳跃的最少次数，所以需要知道什么时候必须跳跃的边界；

第四道需要划分开当前字符串段的最少次数，所以需要知道当前字母出现的最远位置。

复杂一些，现在还想得不那么明白。慢慢品味。



[121. 买卖股票的最佳时机](https://leetcode.cn/problems/best-time-to-buy-and-sell-stock/)

“最佳时机”的直觉是在最低点买入，在之后的最高点卖出。

因此对于每个我们正在遍历的价格，**维护其之前的历史最低点**，**计算出在当前卖出的利润**，从而遍历获得最佳利润。

```python
class Solution:
    def maxProfit(self, prices: List[int]) -> int:
        lowest = float('inf')
        res = 0
        for price in prices:
            lowest = min(lowest, price)
            res = max(res, price - lowest)
        return res
```



55 跳跃游戏

遍历下标，维护一个当前最远可达下标。

如果最远可达下标小于当前下标，则返回False，否则最远可达下标更新。

感觉这两道题与其说是贪心，不如说是维护一个最值。

<div class="algoviz" data-module="lc55-跳跃游戏" data-title="55 跳跃游戏 · 步骤可视化"></div>
```
class Solution:
    def canJump(self, nums: List[int]) -> bool:
        maxReach = 0
        for i in range(len(nums)):
            if maxReach < i:
                return False
            maxReach = max(maxReach, i + nums[i])
            if maxReach >= len(nums) - 1:
                return True
        return maxReach >= len(nums) - 1
```

45 跳跃游戏 II

写了一个不好的dp，维护从某个下标跳跃到最后一个下标的最小步数。

<div class="algoviz" data-module="lc45-跳跃游戏-ii" data-title="45 跳跃游戏 II · 步骤可视化"></div>
```
class Solution:
    def jump(self, nums: List[int]) -> int:
        minStep = [float('inf')] * len(nums)
        minStep[-1] = 0
        for i in range(len(nums) - 2, -1, -1):
            # 对于某个下标i, 遍历它可达的所有下标, 选取其中跳跃到最后下标的最小值.
            for j in range(i + 1, min(len(nums), i + nums[i] + 1)):
                minStep[i] = min(minStep[i], minStep[j] + 1)
        return minStep[0]
```

然后写了贪心。

贪心策略是，cur_end维护当前jumps数能够跳到的最远位置。

<div class="algoviz" data-module="lc45-跳跃游戏-ii-v2" data-title="45 跳跃游戏 II · 步骤可视化"></div>
```
class Solution:
    def jump(self, nums: List[int]) -> int:
        n = len(nums)
        if n == 1:
            return 0
        jumps = 0
        cur_end = 0
        farthest = 0
        for i in range(n - 1):
            farthest = max(farthest, i + nums[i])

            if i == cur_end: # 需要多跳一次
                jumps += 1
                cur_end = farthest

                # 注意这个剪枝不能写在farthest更新的下一行, 因为需要先更新完jump数.
                if cur_end >= n - 1:
                    break
        return jumps
```

763 划分字母区间

在遍历到每个字母时，更新当前字母的最远位置。如果当前位置已经达到最远位置，则划分成一段。

<div class="algoviz" data-module="lc763-划分字母区间" data-title="763 划分字母区间 · 步骤可视化"></div>
```
class Solution:
    def partitionLabels(self, s: str) -> List[int]:
        last_pos = {}
        for i, ch in enumerate(s):
            last_pos[ch] = i
        res = []
        start = 0
        end = 0
        for i, ch in enumerate(s):
            end = max(end, last_pos[ch])
            if i == end:
                res.append(end - start + 1)
                start = i + 1
        return res
```

### 专题15 动态规划

动态规划的本质就是填表格查表格。

某个问题可以由一些子问题的值得到，所以查子问题的表格，然后填入该问题的表格。



[300. 最长递增子序列](https://leetcode.cn/problems/longest-increasing-subsequence/)

**解法二**：贪心+二分查找

维护一个递增的数组 `tails` ，其中 `tails[i]` 表示长度为 `i+1` 的递增子序列的最小末尾值。

则维护方式是：每次来一个新的数，都**在 `tails` 数组中找到第一个大于等于它的数**。如果存在，则覆盖。

> 以输入序列 [0, 8, 4, 12, 2] 为例：
>
> - 第一步插入 0，d = [0]；
> - 第二步插入 8，d = [0, 8]；
> - 第三步插入 4，d = [0, 4]；
> - 第四步插入 12，d = [0, 4, 12]；
> - 第五步插入 2，d = [0, 2, 12]。

时间复杂度：$O(n \log n)$ ，空间复杂度：$O(n)$

```python
class Solution:
    def lengthOfLIS(self, nums: List[int]) -> int:
        tails = [] # 递增的, tails[i]表示长度为i+1的递增子序列的最小末尾值
        for num in nums:
            left, right = 0, len(tails)
            while left < right:
                mid = (left + right) // 2
                if tails[mid] < num: # 二分目的: 在tails中找到第一个>=num的值
                    left = mid + 1
                else:
                    right = mid

            if left == len(tails):
                tails.append(num)
            else:
                tails[left] = num
        return len(tails)
```

**解法一**：动态规划

当前位置的最长递增子序列长度可以由它之前的所有位置转移得到。

**注意每个位置的递增子序列长度不小于1**。

时间复杂度：$O(n^2)$ ，空间复杂度：$O(n)$

```python
class Solution:
    def lengthOfLIS(self, nums: List[int]) -> int:
        n = len(nums)
        dp = [1] * (n + 10)
        for i, num in enumerate(nums):
            for j in range(i):
                if num > nums[j]:
                    dp[i] = max(dp[i], dp[j] + 1)
        return max(dp)
```



70 爬楼梯

<div class="algoviz" data-module="lc70-爬楼梯" data-title="70 爬楼梯 · 步骤可视化"></div>
```
class Solution:
    def climbStairs(self, n: int) -> int:
        # 问题的解由子问题的解组成.
        # a[n] = a[n - 1] + a[n - 2]
        a = [1, 1]
        for i in range(2, n + 1):
            a.append(a[i - 1] + a[i - 2])
        return a[n]
```

118 杨辉三角

<div class="algoviz" data-module="lc118-杨辉三角" data-title="118 杨辉三角 · 步骤可视化"></div>
```
class Solution:
    def generate(self, numRows: int) -> List[List[int]]:
        if numRows == 1:
            return 1
        elif numRows == 2:
            return [[1], [1, 1]]
        else:
            cur_list = [[1], [1, 1]]
            for i in range(2, numRows):
                cur_list.append([1] * (i + 1))
                # eg. i = 3时, j从1到2
                for j in range(1, i):
                    cur_list[i][j] = cur_list[i - 1][j - 1] + cur_list[i - 1][j]
            return cur_list
```

198 打家劫舍

<div class="algoviz" data-module="lc198-打家劫舍" data-title="198 打家劫舍 · 步骤可视化"></div>
```
class Solution:
    def rob(self, nums: List[int]) -> int:
        if len(nums) == 1:
            return nums[0]
        dp = [0] * len(nums)
        dp[0] = nums[0]
        dp[1] = max(nums[0], nums[1])
        for i in range(2, len(nums)):
            dp[i] = max(dp[i - 2] + nums[i], dp[i - 1])
        return dp[len(nums) - 1]
```

由于只依赖于上两个状态，因此可以只用两个变量滚动，实现空间的简化。

<div class="algoviz" data-module="lc198-打家劫舍-v2" data-title="198 打家劫舍 · 步骤可视化"></div>
```
class Solution:
    def rob(self, nums: List[int]) -> int:
        if len(nums) == 1:
            return nums[0]

        prev2 = nums[0]
        prev1 = max(nums[0], nums[1])
        for i in range(2, len(nums)):
            cur = max(prev2 + nums[i], prev1)
            prev2 = prev1
            prev1 = cur
        return prev1
```

279 完全平方数

递推做法。

<div class="algoviz" data-module="lc279-完全平方数" data-title="279 完全平方数 · 步骤可视化"></div>
```
class Solution:
    def numSquares(self, n: int) -> int:
        dp = [float('inf')] * (n + 1)
        dp[0], dp[1] = 0, 1
        for i in range(2, n + 1):
            for j in range(1, int(sqrt(i)) + 1):
                dp[i] = min(dp[i], dp[i - j * j] + 1)
        return dp[n]
```

以下是一个带cache的递归做法，奇慢，但是能过。

这道题递归不如递推，因为从0到n的状态一定都需要计算（每个数至少可以减1*1），没有可以剪枝的状态。

<div class="algoviz" data-module="lc279-完全平方数-v2" data-title="279 完全平方数 · 步骤可视化"></div>
```
class Solution:
    def numSquares(self, n: int) -> int:
        if n == 0:
            return 0
        elif not hasattr(self, 'numCache'):
            self.numCache = [float('inf')] * (n + 1)
            self.numCache[0] = 0
        elif hasattr(self, 'numCache') and self.numCache[n] != float('inf'):
            return self.numCache[n]

        minCnt = n
        for i in range(1, int(sqrt(n)) + 1):
            minCnt = min(minCnt, self.numSquares(n - i * i) + 1)
        self.numCache[n] = minCnt
        return minCnt
```

322 零钱兑换

先来一个不带cache的递归，当然TLE过不了。

<div class="algoviz" data-module="lc322-零钱兑换" data-title="322 零钱兑换 · 步骤可视化"></div>
```
class Solution:
    def coinChange(self, coins: List[int], amount: int) -> int:
        if amount < 0:
            return -1
        elif amount == 0:
            return 0
        minCnt = float('inf')
        for coin in coins:
            cnt = self.coinChange(coins, amount - coin)
            if cnt == -1:
                continue
            minCnt = min(minCnt, cnt + 1)
        if minCnt == float('inf'):
            return -1
        else:
            return minCnt
```

接下来给这个递归加个cache就能过了，只是慢一点。

<div class="algoviz" data-module="lc322-零钱兑换-v2" data-title="322 零钱兑换 · 步骤可视化"></div>
```
class Solution:
    def coinChange(self, coins: List[int], amount: int) -> int:
        if amount < 0:
            return -1
        elif amount == 0:
            return 0
        elif not hasattr(self, 'coinCache'):
            self.coinCache = [float('inf')] * (amount + 1)
            self.coinCache[0] = 0
        elif hasattr(self, 'coinCache') and self.coinCache[amount] != float('inf'):
            return self.coinCache[amount]

        minCnt = float('inf')
        for coin in coins:
            cnt = self.coinChange(coins, amount - coin)
            if cnt == -1:
                continue
            minCnt = min(minCnt, cnt + 1)
        if minCnt == float('inf'):
            self.coinCache[amount] = -1
            return -1
        else:
            self.coinCache[amount] = minCnt
            return minCnt
```

那么这样的递推比递归快多了。顺手加了个小剪枝。

```
class Solution:
    def coinChange(self, coins: List[int], amount: int) -> int:
        if amount == 0:
            return 0
        coins.sort() # 顺手排个升序, 方便continue改成break
        coinCache = [float('inf')] * (amount + 1)
        coinCache[0] = 0
        for i in range(1, amount + 1):
            for coin in coins:
                if i - coin < 0:
                    break
                coinCache[i] = min(coinCache[i], coinCache[i - coin] + 1)

        if coinCache[amount] == float('inf'):
            return -1
        else:
            return coinCache[amount]
```

139 单词拆分

这里转移的实体是字符串。同构的实体是结尾到下标i的字符串段，我们要看的是同构实体是否可以拆分。

那么对于某个特定的同构实体，我们只需要遍历它所有可能的拆分点、看是否有拆分点前半部分是同构实体，后半部分在字典中即可。

<div class="algoviz" data-module="lc139-单词拆分" data-title="139 单词拆分 · 步骤可视化"></div>
```
class Solution:
    def wordBreak(self, s: str, wordDict: List[str]) -> bool:
        # 对于字符串的dp, 要意识到字符串一般都是从左往右遍历下标.
        # 那么对于结尾为i(开)的字符串s[0..i],可以分割意味着存在分割点j, 使得dp[j]=True且s[j..i]在wordDict中.
        wordDict = set(wordDict) # 会快很多
        n = len(s)
        dp = [False] * (n + 1)
        dp[0] = True # 空串
        for i in range(n + 1):
            for j in range(i):
                if dp[j] and s[j:i] in wordDict:
                    dp[i] = True
        return dp[n]
```

总之dp可以念这样一句话：

“对于特定同构实体，它可以由哪些同构实体转移得到”。

152 乘积最大子数组

到i的乘积最大值，可能由最大值、最小值或不选，三种情况转移得到。容易漏解。

<div class="algoviz" data-module="lc152-乘积最大子数组" data-title="152 乘积最大子数组 · 步骤可视化"></div>
```
class Solution:
    def maxProduct(self, nums: List[int]) -> int:
        # 到i的乘积最大值, 可能由**最大值或最小值**转移得到.
        res = nums[0]
        prev_max = prev_min = nums[0]

        for i in range(1, len(nums)):
            curr_max = max(nums[i], prev_max * nums[i], prev_min * nums[i])
            curr_min = min(nums[i], prev_max * nums[i], prev_min * nums[i])
            res = max(res, curr_max)
            prev_max, prev_min = curr_max, curr_min

        return res
```

416 分割等和子集

将分割等和子集，转化成在集合中选取一些元素，使得它们的和恰好等于总和的二分之一。这样的约束问题恰好是0-1背包的变种，可以设置dp为“前i个元素是否能够得到和为j”。

<div class="algoviz" data-module="lc416-分割等和子集" data-title="416 分割等和子集 · 步骤可视化"></div>
```
class Solution:
    def canPartition(self, nums: List[int]) -> bool:
        total = sum(nums)
        if total % 2:
            return False
        target = total // 2
        n = len(nums)

        # 前i个元素和为target
        dp = [[False] * (target + 1) for _ in range(n + 1)]
        for i in range(n + 1):
            dp[i][0] = True

        for i in range(1, n + 1):
            # 这里前i个元素, 实际要添加的元素是nums[i - 1]
            for j in range(1, target + 1):
                if j < nums[i - 1]:
                    dp[i][j] = dp[i - 1][j]
                else:
                    dp[i][j] = dp[i - 1][j] or dp[i - 1][j - nums[i - 1]]

        return dp[n][target]
```

之后因为每一行的表格都只依赖于上一行的表格，再使用类似的二维背包转一维背包的空间优化，**去掉行下标，然后列下标的遍历一定只能倒着来。**

这个一维dp空间优化本质是因为，j - num使用的是“上一行”的状态（前i个由前i-1个决定），从大到小遍历j的话可以保证这样填入每处dp时使用的都是“上一行”的状态。

而如果从小到大遍历，则j - num可能已经被更新为了“新一行”的状态，而“同一行”的状态互相转移（前i个由前i个决定）是混乱且不允许的。

最后再整体审视一下这个背包。其实时间复杂度是完全没有变的，转移关系也是完全没有变的。外层仍然需要遍历所有“前i个”，只是内层为了配合空间上的优化，所用的遍历顺序发生了变化。

想清楚了的话，下面两句话不言自明：

1. 二维01背包，内层循环正着倒着遍历都行。
2. 优化为一维01背包后，内层循环只能倒着遍历。

<div class="algoviz" data-module="lc2-优化为一维01背包后-内层循环只能倒着遍历" data-title="2 优化为一维01背包后，内层循环只能倒着遍历。 · 步骤可视化"></div>
```
class Solution:
    def canPartition(self, nums: List[int]) -> bool:
        total = sum(nums)
        if total % 2:
            return False

        target = total // 2

        # dp[j] 表示能否选出和为 j 的子集
        dp = [False] * (target + 1)
        dp[0] = True  # 和为0总是可以

        for num in nums:
            # 必须从大到小遍历，避免重复使用同一个数
            for j in range(target, num - 1, -1):
                if dp[j - num]:
                    dp[j] = True

            # 提前结束
            if dp[target]:
                return True

        return dp[target]
```



[32. 最长有效括号](https://leetcode.cn/problems/longest-valid-parentheses/)

方法二：**计数器**

一段子串是有效括号串，当且仅当以下两个条件：

- 它的任意前缀中 `'(' >= ')'`（从左到右不会出现右括号过多）

- 它的任意后缀中 `')' >= '('`（从右到左不会出现左括号过多）

所以可以从前往后遍历一遍、从后往前遍历一遍，各自使用计数器计数。

记得在第二次遍历之前把计数器清空哦。

时间复杂度：$O(n)$ ，空间复杂度：$O(1)$

```python
class Solution:
    def longestValidParentheses(self, s: str) -> int:
        max_len = 0
        left = right = 0 # 计数器
        for ch in s:
            if ch == '(':
                left += 1
            else:
                right += 1
            if left == right:
                max_len = max(max_len, left * 2)
            elif left < right: # 不满足前缀条件
                left = right = 0

        left = right = 0 # 第二次遍历之前一定要重置!
        for ch in reversed(s):
            if ch == '(':
                left += 1
            else:
                right += 1
            if left == right:
                max_len = max(max_len, left * 2)
            elif left > right: # 不满足后缀条件
                left = right = 0
        
        return max_len
```

方法一：**栈**

栈里面存入最后一个未被匹配的括号位置。

栈里面默认存入的 `-1` 是为了特殊情况，不能改成其他值。

例如 `s = '()'` ，则此时应该返回的长度为2，因此 `i = 1` 时应将 `res` 更新为2，即此时 `1 - stk[-1] = 2` ，故 `stk[-1] = -1` 。

时间复杂度：$O(n)$，空间复杂度：$O(n)$

```python
class Solution:
    def longestValidParentheses(self, s: str) -> int:
        stk = [-1]
        res = 0
        for i, ch in enumerate(s):
            if ch == '(':
                stk.append(i)
            else:
                stk.pop()
                if not stk:
                    stk.append(i)
                res = max(res, i - stk[-1])
        return res
```

### 专题16 多维动态规划

[62. 不同路径](https://leetcode.cn/problems/unique-paths/)

方法三：**组合数**

机器人总共需要走 $m + n - 2$ 步，其中 $m - 1$ 步往下走、$n - 1$ 步往右走。所以答案为组合数 $C_{m+n-2}^{m-1}$ 。

时间复杂度：$O(\min \{m, n\})$ ，空间复杂度：$O(1)$ 。

```python
class Solution:
    def uniquePaths(self, m: int, n: int) -> int:
        return math.comb(m + n - 2, min(m, n) - 1)
```

方法二：**滚动数组优化DP**

由于 `dp[i][j] = dp[i - 1][j] + dp[i][j - 1]` 这一式子中**第 `i` 行的值只与第 `i - 1` 行和第 `i` 行的值有关**，符合条件，可以使用滚动数组优化空间复杂度到 $O(n)$ 。

注意：**滚动数组仅仅是优化了空间复杂度的技巧**。而这道题的DP解法需要遍历所有位置这件事的时间复杂度是降不下来的。

时间复杂度：$O(mn)$ ，空间复杂度：$O(n)$

> 我们可以想象一下滚动数组的直觉：
>
> 刚刚开始处理第 `i` 行时，**滚动数组保存着第 `i - 1` 行的状态**，天生方便复用第 `i - 1` 行的值。
>
> 那么问题来了：我们处理**第 `j` 列时还对第 `j - 1` 列有依赖**呢，这个怎么办呀？
>
> 答案就在谜面上。如果我们在遍历 `j` 时是**从左往右遍历**，则位置 `[i][j - 1]` 的状态同样已经更新好了。
>
> 总结：
>
> 滚动数组去掉了所有的 `[i]` 下标，然后根据 `j` 的依赖关系确定遍历 `j` 时是从左往右还是从右往左。
>
> 这是优化空间复杂度的技巧，而对时间复杂度没有任何助益。（我们仍然是做了 $mn$ 次操作，只是复用了 $n$ 个格子！）
>
> 备注：
>
> 如果第 `j` 列依赖第 `j + 1` 列，则内层循环需要改成从右往左遍历。如朴素背包问题。

```python
class Solution:
    def uniquePaths(self, m: int, n: int) -> int:
        dp = [1] * n

        for i in range(1, m):
            for j in range(1, n):
                dp[j] += dp[j - 1]
        return dp[n - 1]
```

方法一：**朴素DP**

首先，我们知道第0行和第0列都只有一条路径，所以这些位置初始化为1。

然后有 `dp[i][j] = dp[i - 1][j] + dp[i][j - 1]` 。可以写出如下的优化前DP代码。

时间复杂度：$O(mn)$ ，空间复杂度：$O(mn)$ 。

```python
class Solution:
    def uniquePaths(self, m: int, n: int) -> int:
        # 初始化第0行和第0列为全1
        dp = [[1] * n] + [[0] * n for _ in range(m - 1)]
        for i in range(1, m):
            dp[i][0] = 1

        for i in range(1, m):
            for j in range(1, n):
                dp[i][j] = dp[i - 1][j] + dp[i][j - 1]
        return dp[m - 1][n - 1]
```





64 最小路径和

<div class="algoviz" data-module="lc64-最小路径和" data-title="64 最小路径和 · 步骤可视化"></div>
```
class Solution:
    def minPathSum(self, grid: List[List[int]]) -> int:
        m, n = len(grid), len(grid[0])
        dp = [[float('inf')] * n for _ in range(m)]
        dp[m - 1][n - 1] = grid[m - 1][n - 1]
        for i in range(m - 2, -1, -1):
            dp[i][n - 1] = dp[i + 1][n - 1] + grid[i][n - 1]
        for j in range(n - 2, -1, -1):
            dp[m - 1][j] = dp[m - 1][j + 1] + grid[m - 1][j]

        for i in range(m - 2, -1, -1):
            for j in range(n - 2, -1, -1):
                # 下面右面二选一
                dp[i][j] = min(dp[i + 1][j], dp[i][j + 1]) + grid[i][j]
        return dp[0][0]
```

5 最长回文子串

很干净的子串遍历和自底向下填表格问题，值得记忆。

记得像Dijkstra说的那样，左闭右开。

顺手推一下循环上界：

(1) 我们使用的字符子串是 `s[i:i+length]`，所以有 i + length <= n 得到内层 i < n - length + 1。

(2) 最大的子串应为 s[0:n]，此时i = 0，length = n，所以有外层 length < n + 1。

<div class="algoviz" data-module="lc5-最长回文子串" data-title="5 最长回文子串 · 步骤可视化"></div>
```
class Solution:
    def longestPalindrome(self, s: str) -> str:
        n = len(s)
        if n == 1:
            return s

        # dp[i][j]表示s[i:j+1]是否回文
        dp = [[False] * n for _ in range(n)]
        start = 0 # 用于返回解
        maxlen = 1

        for i in range(n):
            dp[i][i] = True

        # 字符串是s[i:i+length]
        # 字符串最后一个字符是s[i + length - 1]
        for length in range(2, n + 1):
            for i in range(n - length + 1):
                j = i + length - 1
                if s[i] == s[j]:
                    if length == 2:
                        dp[i][j] = True
                    else:
                        dp[i][j] = dp[i+1][j-1]
                    if dp[i][j] and length > maxlen:
                        maxlen = length
                        start = i
        return s[start:start + maxlen]
```

1143 最长公共子序列

皮一下，内层只写一行。

除了转移逻辑，记得处理一下边界。这里字符串下标使用实际下标，但dp使用下标+1，处理边界。

```
class Solution:
    def longestCommonSubsequence(self, text1: str, text2: str) -> int:
        # i是s1的结束位置, j是s2的结束位置
        m, n = len(text1), len(text2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                dp[i][j] = dp[i - 1][j - 1] + 1 if text1[i - 1] == text2[j - 1] else max(dp[i - 1][j], dp[i][j - 1])
        return dp[m][n]
```

[72. 编辑距离](https://leetcode.cn/problems/edit-distance/)

方法二：**滚动数组优化空间**

这玩意一口气依赖了三个元素（事实上是对角线形式的依赖），但是仍然可以用滚动数组优化空间复杂度。

其关键是找到并维护好这些关系：

- **用一个 `prev` 变量存储 `[i - 1][j - 1]` 位置的元素。**
- `dp[i][j - 1]` 元素当前的存储是 `dp[j - 1]` 。
- `dp[i - 1][j]` 元素当前的存储是 `dp[j]` 。

为了维护：

在设置 `dp[j]` 的值之前，需要把 `dp[j]` 的值保存下来（相当于 `dp[i - 1][j - 1]`）。

（想一下二维数组就好想了）`dp[i][0]` 直接保存给 `prev` ，再设置 `dp[i][0]` 的值为 `i` ；

在循环中因为 `prev` 要使用，所以保存给 `tmp` ，等用完 `prev` 了再传给它。

时间复杂度：$O(mn)$，空间复杂度：$O(n)$

```python
class Solution:
    def minDistance(self, word1: str, word2: str) -> int:
        # 关键: 使用右边界, 所以需要多开一个, 而且判断时需要用-1
        m, n = len(word1), len(word2)
        # dp[i][j] 代表将word1[:i]转化成word2[:j]的最小操作数
        dp = [j for j in range(n + 1)]

        for i in range(1, m + 1):
            prev = dp[0]
            dp[0] = i # 用来存储当前行的dp初值
            for j in range(1, n + 1):
                tmp = dp[j]
                if word1[i - 1] == word2[j - 1]:
                    dp[j] = prev
                else:
                    dp[j] = 1 + min(dp[j], dp[j - 1], prev)
                prev = tmp
        return dp[n]
```



方法一：**朴素动态规划**

不要被题目吓到。其实就是最长公共子序列那种感觉。题目的三种方式只是三种转移。

十分经典的题目，从CS61A的练习题里就出现过。

时间复杂度：$O(mn)$，空间复杂度：$O(mn)$

```python
class Solution:
    def minDistance(self, word1: str, word2: str) -> int:
        # 关键: 使用右边界, 所以需要多开一个, 而且判断时需要用-1
        m, n = len(word1), len(word2)
        # dp[i][j] 代表将word1[:i]转化成word2[:j]的最小操作数
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if word1[i - 1] == word2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[m][n]
```



[312. 戳气球](https://leetcode.cn/problems/burst-balloons/)

十分经典的一道题目，其关键是把戳气球问题，转化为**开区间 `(i, j)` 的遍历问题**。

对于开区间 `(i, j)` ，`dp[i][j]` 表示这一段区间里戳气球能够得到的最大得分。

拆成最优子问题，即以 $k \in (i, j)$ 为划分点，左右两段的最大得分、加上当前划分点对应的得分。

> 区间遍历的写法：最外层遍历长度、内层循环遍历起始点。

时间复杂度：$O(n^3)$ 。空间复杂度：$O(n^2)$ 。

```python
class Solution:
    def maxCoins(self, nums: List[int]) -> int:
        points = [1] + nums + [1]
        n = len(points)
        dp = [[0] * n for _ in range(n)]
        for length in range(2, n): # 开区间 (i, j)
            for i in range(0, n - length):
                j = i + length
                for k in range(i + 1, j):
                    dp[i][j] = max(dp[i][j], points[i] * points[k] * points[j] + dp[i][k] + dp[k][j])
        return dp[0][n - 1]
```



### 专题17 技巧

136 只出现一次的数字

把出现偶数次的用异或消除掉。

<div class="algoviz" data-module="lc136-只出现一次的数字" data-title="136 只出现一次的数字 · 步骤可视化"></div>
```
class Solution:
    def singleNumber(self, nums: List[int]) -> int:
        res = 0
        for num in nums:
            res ^= num
        return res
```

169 多数元素

寻找众数的方法。通过投票，赞同当前提议则投正面票，反对当前提议则投负面票，最后留下的就是众数。

<div class="algoviz" data-module="lc169-多数元素" data-title="169 多数元素 · 步骤可视化"></div>
```
class Solution:
    def majorityElement(self, nums: List[int]) -> int:
        count = 0
        majority = -1
        for num in nums:
            if count == 0:
                majority = num
                count += 1
            elif majority == num:
                count += 1
            else:
                count -= 1
        return majority
                
```

75 颜色分类

其实是中间指针用于扫描，把元素分配到左边指针和右边指针的动态空间的过程。

关于cur指针是否移动，左右指针有所区别：

如果交换到l指针，

一开始：它们都是0，则交换后cur指向的元素（同时也是l指向的元素）位置已完成处理，cur可以移动。

过程中：l指针指向判断过的元素，cur与它交换后两个指针都是处理过的元素，cur可以移动。

如果交换到r指针，

一开始：r指针指向的未处理，cur指针与它交换后，r指针指向的已处理，但是cur指针指向的元素没有处理。所以cur不移动。

<div class="algoviz" data-module="lc75-颜色分类" data-title="75 颜色分类 · 步骤可视化"></div>
```
class Solution:
    def sortColors(self, nums: List[int]) -> None:
        """
        Do not return anything, modify nums in-place instead.
        """
        # l和r是待分配位置, cur是正在扫描的元素
        l, cur, r = 0, 0, len(nums) - 1
        while cur <= r:
            if nums[cur] == 0:
                nums[cur], nums[l] = nums[l], nums[cur]
                l += 1
                cur += 1
            elif nums[cur] == 2:
                nums[cur], nums[r] = nums[r], nums[cur]
                r -= 1
                # 注意！！这里cur不增加, 因为交换过来的数还没处理
            else:
                cur += 1
                
```

31 下一个排列

三步走：定位升序对，找最小元素，交换并翻转。

定位升序对 `(nums[i], nums[i + 1])`，

在 `i` 右侧找大于 `nums[i]` 的最小元素，

交换 `nums[i]` 和最小元素后把 `i`右侧翻转。

<div class="algoviz" data-module="lc31-下一个排列" data-title="31 下一个排列 · 步骤可视化"></div>
```
class Solution:
    def reverseNums(self, nums, i, j):
        while i < j:
            nums[i], nums[j] = nums[j], nums[i]
            i += 1
            j -= 1

    def nextPermutation(self, nums: List[int]) -> None:
        """
        Do not return anything, modify nums in-place instead.
        """
        # [1,2,3] [1,3,2] [2,1,3] [2,3,1] [3,1,2] [3,2,1]
 
        # 定位从右往左第一个升序对 (nums[i], nums[i + 1]),
        # 在nums[i+1:]中取大于nums[i]的最小值, 将最小值与nums[i]交换.
        # 然后翻转nums[i+1:].
        n = len(nums)
        exist = False
        for i in range(n - 2, -1, -1):
            # 定位升序对
            if nums[i] < nums[i + 1]:
                exist = True
                # 在i右边找最小元素作为待交换的元素, 注意有重复时应选择右边的
                min_j = i + 1
                for j in range(i + 2, n):
                    if nums[i] < nums[j] <= nums[min_j]:
                        min_j = j
                # 交换, 然后把i右边翻转
                nums[i], nums[min_j] = nums[min_j], nums[i]
                self.reverseNums(nums, i + 1, len(nums) - 1)
                break

        if not exist:
            self.reverseNums(nums, 0, len(nums) - 1)
```

[287. 寻找重复数](https://leetcode.cn/problems/find-the-duplicate-number/)

方法一：**原地哈希**。即利用数组的值作为索引，**映射**到数组自身。如果有两个不同的数组元素映射到相同的位置（我们可以通过负值判断），则该位置就是我们所求的重复数。

既然要作为索引，我们所有使用和返回的值都应该是负值的绝对值。

时间复杂度：$O(n)$ ，空间复杂度：$O(1)$ 。

```python
class Solution:
    def findDuplicate(self, nums: List[int]) -> int:
        n = len(nums)
        for i in range(n):
            absval = abs(nums[i])
            if nums[absval] < 0:
                return absval
            nums[absval] = -nums[absval]
        return -1
```

方法二：**快慢指针**。同样用映射的思想，我们可以把数组理解成链表，那么重复数就意味着**有两个指针在链表上映射到了同一个节点**，也即链表有**环**。从而我们只要：

- 首先用快慢指针找到相遇点，
- 然后用一个指针指向起点、另一个指针指向相遇点，两个指针速度相同（均为慢指针），
- 它们再次相遇的位置就是环入口。

时间复杂度：$O(n)$ ，空间复杂度：$O(1)$ 。

```python
class Solution:
    def findDuplicate(self, nums: List[int]) -> int:
        slow, fast = nums[0], nums[0]
        while True:                  # 至少执行一次, 排除掉一开始相同的情况
            slow = nums[slow]        # x = nums[x]相当于x = x.next, 反正是映射了一次
            fast = nums[nums[fast]]
            if slow == fast:
                break
        slow = nums[0]
        while slow != fast:
            slow = nums[slow]
            fast = nums[fast]
        return slow
```

另外还有一种方式是利用二分进行值域查找。重复数所位于的区间性质是“个数比元素值大”。

时间复杂度：$O(n \log n)$ ，空间复杂度：$O(1)$ 。

```
class Solution:
    def findDuplicate(self, nums: List[int]) -> int:
        # eg. [1, 2, 2, 3, 4]
        # 如果某个值(如3), 小于等于它的个数比这个数本身要大, 则重复数位于这一段.
        l, r = 1, len(nums) - 1
        while l < r:
            mid = (l + r) // 2
            # 计数小于等于它的个数
            cnt = 0
            for num in nums:
                if num <= mid:
                    cnt += 1
            # 重复数是否位于左半段
            if cnt > mid:
                r = mid
            else:
                l = mid + 1
        return l
```

> 写到这里，突然有所感慨。
>
> HOT 100是我前后刷了三次往上的题单：
>
> - 第一遍是为了学Python、数据结构与算法。囫囵吞枣，只是对一小部分题目和书写结构留下一个模模糊糊的印象。像是抄了一遍书，为之后多多少少留下了一点熟悉感。
> - 第二遍则正儿八经地尝试去理解每一处细节。这一遍是按照LeetCode HOT 100的分类一类一类刷的。这一遍刷得很慢，完全是推着自己硬要写下去才能写得下去。一天可能看个几道就开始大脑过载，记下来的东西也不知道哪些是重点、哪些不是重点——仿佛这些笔记自己不会再看一样。事实也如此，这些笔记之后一次也没有看过。可是留下的熟悉感竟然要多一些。
> - 第三遍就是出于实习面试的功利目的，需要快、需要熟，那么不就只能背了！这一遍是随机从HOT 100抽的（当然重点抽了Hard和Medium）。这时候已经认真完整学过王道的数据结构体系、学过算法导论的体系、还学过一遍洛谷基础篇的体系，似乎那些东西拿到手边都能看懂，只是随便给我一个题，我还是不敢写。不敢写、不敢写，万事万物就卡在一个不敢上面。反正结果上，随便抽一道、能如同“渐进式披露”一般摸个大概出来，也许有些细节还是得调一下、补一下、不一定能一遍AC。但至少现在抽一道题过来，至少是敢动笔了，也多多少少记得DFS、BFS、回溯、单调栈什么的，大概是什么样子。
> - 也许有些关口总是要有什么推一把的吧。人的可塑性还是太好了——我一个完全不会钢琴的、以前也只打过2k和4k的玩家，打打osu!打多了，也能打点新手入门7k谱了。**人的无限性总是被世界的有限性给约束住**，然后或许会因此以为人是有限的——
> - 于是，下一首乐曲即将奏响。

上一篇：[[algorithm-4|04 HOT 100（前 50）]]
