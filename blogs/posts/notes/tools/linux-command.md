---
title: 值得顺便掌握一下的那些linux指令
date: 2026-03-10 11:14:01
tags:
- 工具
published: true
hideInList: false
feature: null
isTop: false
---

命令行能够即时地做很多事情，甚至代表一种简洁而切题的计算机哲学。
为了直接进入正题，省略诸如 `cd` 这样的广为人知的基础指令，直接看那些显著提升体验的东西。

<!-- more -->

> edit time: 2026-03-10 11:31:56
## df

用于查看磁盘空间。使用场景比如训模型会保存很多中间文件，可以这样看看需要清理哪些。

使用效果：
比如 `fuse-overlayfs` 是这个实例本身的存储， `shared-nvme` 是它的外接可持久化存储，使用率分别为 `50%` 和 `40%` 。

以下截取需要关注的输出行：

```
$ df
Filesystem              1K-blocks        Used  Available Use% Mounted on
fuse-overlayfs           31457280    15468244   15989036  50% /
/dev/sda3               931347132    85832692  845514440  10% /base
JuiceFS:shared-juice3   104857600    41665660   63191940  40% /root/shared-nvme
```

至于要看哪几个文件最大，可以和 `ncdu` 这样的工具搭配使用。
## grep

查找关键词，关键词可以写正则。
通常和其他指令通过管道搭配使用，简单的用法、强大的功能。

使用效果：

```
$ df | grep /dev
/dev/sda3               931347132    85849780  845497352  10% /base
tmpfs                       65536           0      65536   0% /dev
tmpfs                       65536           0      65536   0% /dev/tty
tmpfs                   528231156           0  528231156   0% /sys/devices/virtual/powercap
/dev/xvdb               308521792    15468280  277308488   6% /etc/hosts
tmpfs                    62914560         112   62914448   1% /dev/shm
```

也可以加 `-i` 参数用于忽略大小写。
## ps

`ps aux` 用于查看当前用户的进程。
但是输出往往很冗长。我只关心我运行的实验，怎么做？
答案很方便：管道加grep！

```
$ ps aux | grep uv
root        7482  0.0  0.0 232328 36616 pts/0    Sl+  11:02   0:00 uv run scripts/batch_sweep.sh --use-wandb --train-data data/tinystories_train.bin --val-data data/tinystories_val.b
root        7512  0.0  0.0 232332 36100 pts/0    Sl+  11:02   0:00 uv run python -m cs336_basics.train --train-data data/tinystories_train.bin --data-dtype uint16 --vocab-size 10000
root        8012  0.0  0.0   3960  1976 pts/1    S+   11:27   0:00 grep --color=auto uv
```

## nvidia-smi

仅适用于使用nvidia显卡的设备。
可以查看GPU情况，包括CUDA版本、有几个设备和设备的使用率等。

使用效果：
这里是单卡5090，CUDA版本为12.8，因此需要安装2.7.1等PyTorch版本。

```shell
nvidia-smi
```

输出中可以关注 `Driver Version`、`CUDA Version`、`GPU Name`、`Memory-Usage` 和 `GPU-Util`，以及 `Processes` 区域中 Python 进程的显存占用。本次输出中的 GPU 为 `NVIDIA GeForce RTX 5090`，显存使用量为 `1114MiB / 32607MiB`，利用率为 `24%`。

## -v -vv -vvv

严格来说这个不是指令，而是一个常见的命令参数。但好用。
有许多工具默认状态给你提供的信息是很有限的，比如 `pip` 。如果加了 `-v` ，它就会给你提供更多的信息；`-vv` 更多更多……
比如你怀疑某个指令是不是卡在网络连接问题上了、又没有信息，就可以加这个参数看看。

使用效果（不加参数）：

```
(pymc) PS > pip install einops
Collecting einops
  Using cached einops-0.8.1-py3-none-any.whl.metadata (13 kB)
Using cached einops-0.8.1-py3-none-any.whl (64 kB)
Installing collected packages: einops
Successfully installed einops-0.8.1
```

使用效果（`-v`）：

```shell
pip install -v einops
```

输出会增加 pip 和 Python 的版本、候选下载链接、Python 版本要求，以及获取包元数据的过程。例如以下输出说明某个版本需要 Python 3.9 以上：

```
Link requires a different Python (3.8.0 not in: '>=3.9')
```

使用效果（`-vv`）：

```shell
pip install einops -vv
```

以下截取网络请求和缓存判断部分：

```
Fetching project page and analyzing links: https://pypi.org/simple/einops/
Getting page https://pypi.org/simple/einops/
Found index url https://pypi.org/simple/
Looking up "https://pypi.org/simple/einops/" in the cache
Request header has "max_age" as 0, cache bypassed
Starting new HTTPS connection (1): pypi.org:443
https://pypi.org:443 "GET /simple/einops/ HTTP/1.1" 304 0
Fetched page https://pypi.org/simple/einops/ as application/vnd.pypi.simple.v1+json
```

`-vvv` 就不说了。肯定更多。

相关：[[csapp-shelllab|Shelllab]]
