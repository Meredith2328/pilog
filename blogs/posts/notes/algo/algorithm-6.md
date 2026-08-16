---
title: 数据结构与算法 · 06 · 继续进行一个LeetCode的刷题
date: 2026-03-02 11:38:24
tags:
- 数据结构与算法
published: false
hideInList: true
feature: null
isTop: false
chapters_per_page: 1
---



[3499. 操作后最大活跃区段数 I](https://leetcode.cn/problems/maximize-active-section-with-trade-i/)

tag: 滑动窗口

原题目翻译一下就是，如果有连续1-连续0-连续1-连续0-连续1这样的段落，则可以把这两段连续0转化成连续1。我们可以进行一次这样的转化操作，求转化后的1的最大总个数。

因此简单模拟一下这个过程：首先把原始的 `t` 利用双指针处理成连续块放进 `group` ，然后直接判断 `group` 是不是连续的1-0-1-0-1这样的模式。

时间复杂度：$O(n)$ ，空间复杂度：$O(n)$ （最坏情况是每个连续块都只有一个字符）

但实际跑下来比官方解法的常数要高。

```python
class Solution:
    def maxActiveSectionsAfterTrade(self, s: str) -> int:
        original_cnt = s.count('1')
        t = '1' + s + '1'
        group = []

        i = 0
        while i < len(t): # 这一段双指针相当于把连续区块整理成group
            j = i
            while j < len(t) and t[j] == t[i]: # 连续区块 [i, j)
                j += 1
            length = j - i
            group.append((t[i], length)) # 连续区块保存为 (字符, 长度)
            i = j

        max_cnt = 0
        for i in range(2, len(group) - 2):
            if group[i - 2][0] == '1' and group[i - 1][0] == '0' and group[i][0] == '1' and \
            group[i + 1][0] == '0' and group[i + 2][0] == '1':
                max_cnt = max(max_cnt, group[i - 1][1] + group[i + 1][1])
        return original_cnt + max_cnt
```



[2087. 网格图中机器人回家的最小代价](https://leetcode.cn/problems/minimum-cost-homecoming-of-a-robot-in-a-grid/)

tag: 网格问题，不是DP

```python
class Solution:
    def minCost(self, startPos: List[int], homePos: List[int], rowCosts: List[int], colCosts: List[int]) -> int:
        # 由于权值全为非负, 肯定直走的代价是最小的
        res = 0
        x, y = startPos
        tx, ty = homePos
        if tx > x:
            res += sum(rowCosts[x + 1 : tx + 1]) # x那一行不取到
        else:
            res += sum(rowCosts[tx : x])
        
        if ty > y:
            res += sum(colCosts[y + 1 : ty + 1])
        else:
            res += sum(colCosts[ty : y])
        return res
```

