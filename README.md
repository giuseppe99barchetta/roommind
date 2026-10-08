# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      107 |       83 |     22% |32-34, 40-61, 66-67, 73-111, 116-125, 130-153, 158-196 |
| custom\_components/roommind/binary\_sensor.py                      |       57 |        1 |     98% |        77 |
| custom\_components/roommind/climate.py                             |      513 |       91 |     82% |172, 237-254, 337, 344, 350, 355, 358-360, 377, 379, 386, 405-421, 442, 446, 450, 454, 458, 465, 476-483, 490, 492, 498, 549, 566-570, 591, 593, 603, 637-650, 658, 661, 668, 678, 696, 706-709, 712-717, 720, 726, 729-730, 732, 744, 763-765, 772 |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      124 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      207 |        2 |     99% |    53, 85 |
| custom\_components/roommind/control/mpc\_controller.py             |      911 |       51 |     94% |169-170, 176-177, 189-199, 506-508, 526-527, 561-564, 575-582, 595-596, 641, 829, 967-969, 1174, 1256-1268, 1380-1381, 1387, 1664-1665, 1700-1701, 1860, 1862, 1877, 1882, 1887 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      188 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      442 |       17 |     96% |394, 863-878, 989, 1112, 1119-1123 |
| custom\_components/roommind/coordinator.py                         |     1425 |      242 |     83% |119-120, 354, 377-388, 437-444, 561-562, 802, 804, 807-817, 963-964, 973-974, 989-995, 1014, 1019-1020, 1041-1044, 1119, 1135-1136, 1200-1246, 1297-1302, 1377-1379, 1409-1436, 1441-1487, 1489-1503, 1514-1515, 1525, 1527, 1539, 1902-1903, 1911-1916, 1930-1934, 1947, 1971, 1980, 1997-2007, 2009, 2135, 2176, 2234, 2489, 2496-2499, 2502-2510, 2516-2523, 2529-2532, 2540-2543, 2556-2561, 2590-2613, 2706, 2714, 2716, 2718, 2730-2732, 2736-2742, 2746, 2755, 2774, 2776, 2804, 2809, 2811, 2814, 2817, 2861, 2866-2871, 2875, 2908, 2910, 2913, 2916, 2932-2933, 3054, 3074-3082, 3100-3101, 3116-3121, 3138-3139 |
| custom\_components/roommind/diagnostics.py                         |      166 |        0 |    100% |           |
| custom\_components/roommind/fan.py                                 |       81 |       13 |     84% |76-77, 91, 108-112, 115-116, 120-121, 124 |
| custom\_components/roommind/humidifier.py                          |       65 |        7 |     89% |73, 78-79, 87, 95, 98-99 |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/boiler\_manager.py            |      120 |       55 |     54% |47-85, 90, 102-104, 125-126, 128-142, 146-148, 152-164 |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      157 |        2 |     99% |  121, 184 |
| custom\_components/roommind/managers/cover\_manager.py             |      197 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      165 |        2 |     99% |   73, 176 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       54 |        1 |     98% |        28 |
| custom\_components/roommind/managers/energy\_manager.py            |      278 |       13 |     95% |47, 101, 133, 152, 155, 159, 162, 167, 181, 234, 259, 266, 272 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      161 |       41 |     75% |63-70, 91-130, 137, 145, 276, 282 |
| custom\_components/roommind/managers/mold\_manager.py              |      100 |        2 |     98% |   197-198 |
| custom\_components/roommind/managers/power\_budget\_manager.py     |       53 |        6 |     89% |48-49, 51-52, 69, 71 |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/room\_climate.py              |       83 |        3 |     96% |59, 114, 116 |
| custom\_components/roommind/managers/valve\_manager.py             |      123 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_impact\_manager.py    |       17 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       57 |        3 |     95% |     78-80 |
| custom\_components/roommind/repairs.py                             |       36 |        1 |     97% |        45 |
| custom\_components/roommind/select.py                              |       40 |       10 |     75% |     22-33 |
| custom\_components/roommind/sensor.py                              |      150 |        2 |     99% |   69, 250 |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      323 |       37 |     89% |57, 61-62, 70-71, 86, 127, 167-179, 246, 251, 573-574, 576-577, 579-580, 586-598, 650-660 |
| custom\_components/roommind/store.py                               |      201 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      130 |        3 |     98% |31, 158-159 |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/comfort\_insights.py             |       62 |        2 |     97% |     28-29 |
| custom\_components/roommind/utils/device\_utils.py                 |      123 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      156 |        2 |     99% |     78-79 |
| custom\_components/roommind/utils/mold\_utils.py                   |       32 |        0 |    100% |           |
| custom\_components/roommind/utils/night\_mode.py                   |       31 |        5 |     84% |21, 23-24, 31, 46 |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       22 |        0 |    100% |           |
| custom\_components/roommind/utils/room\_insights.py                |       44 |        8 |     82% |25, 28, 53, 55, 57, 59, 61, 63 |
| custom\_components/roommind/utils/schedule\_utils.py               |      164 |        6 |     96% |143-144, 149-150, 158-159 |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       67 |        9 |     87% |72-73, 84, 111-112, 118-121 |
| custom\_components/roommind/websocket\_api.py                      |      310 |        2 |     99% |   852-857 |
| **TOTAL**                                                          | **8034** |  **735** | **91%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/giuseppe99barchetta/roommind/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/giuseppe99barchetta/roommind/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fgiuseppe99barchetta%2Froommind%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.