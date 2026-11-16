# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/giuseppe99barchetta/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      117 |       68 |     42% |35-37, 43-65, 70-71, 77-115, 136-159, 165, 169-173, 184-185, 203-204 |
| custom\_components/roommind/binary\_sensor.py                      |      100 |        1 |     99% |        86 |
| custom\_components/roommind/climate.py                             |      596 |       79 |     87% |186, 259-260, 358, 371, 377-381, 407, 409, 446, 453, 464, 486-488, 490-492, 502-504, 525, 529, 533, 537, 541, 548, 565, 572, 575, 577, 583, 585, 630-631, 635, 640, 642, 685-689, 710, 712, 763-764, 766, 794-807, 815, 818, 825, 835, 853, 863-866, 869-874, 877, 883, 886-887, 922-924, 931 |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      154 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      208 |        2 |     99% |    53, 85 |
| custom\_components/roommind/control/direct\_valve.py               |      124 |        0 |    100% |           |
| custom\_components/roommind/control/mpc\_controller.py             |     1129 |       51 |     95% |217-218, 224-225, 237-247, 558-560, 578-579, 614-617, 628-635, 648-649, 947, 1096-1098, 1104-1105, 1430-1431, 1465, 1590, 1674-1686, 1848-1849, 1855, 2332, 2334, 2349, 2354, 2359 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      269 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      444 |       16 |     96% |396, 878-893, 1004, 1132-1136 |
| custom\_components/roommind/coordinator.py                         |     1838 |      168 |     91% |157-158, 463-466, 488-489, 502-503, 623-630, 698-699, 754-755, 1016, 1018, 1021-1031, 1202-1203, 1272-1275, 1367, 1383-1384, 1609-1610, 1725-1727, 1767, 1823, 1827, 1886, 1894, 1924, 1926, 1934, 1949-1950, 1963, 1977, 2160, 2452-2453, 2461-2463, 2465, 2467, 2469-2470, 2472, 2490, 2514, 2540-2550, 2552, 2679, 2723, 2785, 3017-3018, 3162, 3164, 3379, 3386-3389, 3392-3400, 3406-3413, 3419-3422, 3430-3433, 3446-3451, 3490-3513, 3622, 3630, 3632, 3634, 3646-3648, 3652-3658, 3662, 3671, 3695, 3697, 3725, 3730, 3732, 3735, 3738, 3783, 3797, 3832, 3834, 3837, 3840, 3856-3857, 3983, 4032-4033, 4048-4053, 4070-4071 |
| custom\_components/roommind/diagnostics.py                         |      232 |        3 |     99% |104, 107, 119 |
| custom\_components/roommind/fan.py                                 |       81 |       13 |     84% |76-77, 91, 108-112, 115-116, 120-121, 124 |
| custom\_components/roommind/humidifier.py                          |       65 |        6 |     91% |73, 78-79, 99, 102-103 |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/air\_quality\_manager.py      |      128 |        0 |    100% |           |
| custom\_components/roommind/managers/boiler\_manager.py            |      248 |       23 |     91% |99-100, 115, 121-122, 135, 137, 147-148, 153, 189, 215-216, 222, 234-236, 249-250, 337, 354-356 |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      173 |        2 |     99% |  127, 200 |
| custom\_components/roommind/managers/cover\_manager.py             |      197 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      165 |        2 |     99% |   73, 176 |
| custom\_components/roommind/managers/dehumidifier\_manager.py      |      468 |        8 |     98% |159, 299-300, 423-424, 522, 533-534 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       63 |        1 |     98% |        35 |
| custom\_components/roommind/managers/energy\_manager.py            |      301 |       10 |     97% |60, 165, 168, 175-177, 180, 243, 294, 301 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      164 |        7 |     96% |95, 99, 102, 106, 121, 133, 292 |
| custom\_components/roommind/managers/mold\_manager.py              |      188 |        2 |     99% |     82-83 |
| custom\_components/roommind/managers/power\_budget\_manager.py     |       75 |        6 |     92% |68-69, 73-75, 94 |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/room\_climate.py              |       89 |        4 |     96% |60, 118, 120, 133 |
| custom\_components/roommind/managers/valve\_manager.py             |      125 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_impact\_manager.py    |       17 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |      127 |        3 |     98% |   186-188 |
| custom\_components/roommind/repairs.py                             |       36 |        1 |     97% |        45 |
| custom\_components/roommind/select.py                              |       40 |       10 |     75% |     22-33 |
| custom\_components/roommind/sensor.py                              |      204 |        8 |     96% |74, 226-227, 231-232, 236-237, 343 |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      308 |       37 |     88% |54, 58-59, 67-68, 83, 124, 164-176, 249, 254, 546-547, 549-550, 552-553, 559-571, 623-631 |
| custom\_components/roommind/services/analytics\_stats.py           |      207 |        4 |     98% |86, 115, 123, 165 |
| custom\_components/roommind/services/control\_preview.py           |       45 |        7 |     84% |23, 30-32, 48, 61, 63 |
| custom\_components/roommind/store.py                               |      217 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      150 |        3 |     98% |31, 161-162 |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/comfort\_insights.py             |       82 |        0 |    100% |           |
| custom\_components/roommind/utils/dehumidifier\_forecast.py        |       25 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      152 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      190 |        2 |     99% |  253, 369 |
| custom\_components/roommind/utils/humidity\_targets.py             |       38 |        0 |    100% |           |
| custom\_components/roommind/utils/mold\_utils.py                   |       76 |        4 |     95% |175-176, 179-180 |
| custom\_components/roommind/utils/night\_mode.py                   |       40 |        1 |     98% |        21 |
| custom\_components/roommind/utils/notification\_utils.py           |       85 |        2 |     98% |  162, 165 |
| custom\_components/roommind/utils/presence\_utils.py               |       42 |        0 |    100% |           |
| custom\_components/roommind/utils/room\_insights.py                |       44 |        5 |     89% |25, 53, 59, 61, 63 |
| custom\_components/roommind/utils/schedule\_utils.py               |      155 |        0 |    100% |           |
| custom\_components/roommind/utils/sensor\_utils.py                 |       36 |        2 |     94% |    20, 35 |
| custom\_components/roommind/utils/temp\_utils.py                   |       67 |        9 |     87% |72-73, 84, 111-112, 118-121 |
| custom\_components/roommind/websocket\_api.py                      |      467 |       12 |     97% |359, 373, 816-819, 849-850, 1135-1140, 1421-1422 |
| **TOTAL**                                                          | **10804** |  **594** | **95%** |           |


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