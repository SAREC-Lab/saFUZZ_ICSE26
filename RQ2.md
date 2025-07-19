## RQ2: To what extent can SAFUS detect mode and state-related transition errors in an SuT?



We identified the following Failures:

## Fuzz Scenario Templates

<a name="failures"></a>

| **ID** | **Category** | **Description** | **Type** |
|--------|--------------|-----------------|----------|
| F1 | Mode change ignored from multiple states | Land command ignored in `HOVERING` state. | ● |
| F2 | Mode change ignored from multiple states | `TAKEOFF` ignores human control. | ● |
| F3 | Mode Change Command causes thrashing | Thrashing between states. Upon reactivation, `OFFBOARD` uses old setpoint, causing jerky flight. | ● |
| F4 | Delayed Mode Change | `POSCTL` only acknowledged after `RTL` completed | ● |
| F5 | Unclear requirements | Takeoff ignores `RTL` -- treated as missing requirement. `RTL` should be handled as `LAND` during takeoff | ● |
| F6 | Erratic mode changes caused by interference | GPS Noise created interference causing thrashing between `LAND` and `TAKEOFF` modes | ● |
| F7 | Simulation Error | Simulation Error: Expected to succeed in real-world | ◐ |
| F8 | PX4 issue within mode | PX4 Issue: Failure to disarm upon landing in `STABILIZED` mode | ◐ |
| F9 | Missing logic in Decision Tree. Updated to handle `AUTO.LOITER` & throttle toggle correctly in future tests | Decision Tree did not recognize that Throttle toggling triggers a mode change to `POSCTL` | ○ |
| F10 | Missing logic in Decision Tree. Updated to handle `AUTO.LOITER` & throttle toggle correctly in future tests | Decision Tree did not recognize that `AUTO.LOITER` is handled as `POSCTL` in RotorCraft | ○ |
| F11 | Missing logic in Decision Tree. Updated to handle `AUTO.LOITER` & throttle toggle correctly in future tests | Decision Tree did not recognize that `AUTO.LOITER` is handled as `POSCTL` in RotorCraft | ○ |

**Legend:**  
● True positive mode/state related failure  
○ False positive failure  
◐ Valid failure but not directly associated to mode/state transitions

<br><br><br>


## Fault Trees
<a name="fault-trees"></a>

| **ID** | **Fault Tree Image** | **PX4 Log** |
|--------|----------------------|-------------|
| F1  | ![F1](Figures/Fault-Trees/F1.png)  | [Log](https://review.px4.io/3d?log=47dd2118-69a4-4466-b890-9a2f602867cf) |
| F2  | ![F2](Figures/Fault-Trees/F2.png)  |  [Log](https://review.px4.io/3d?log=86750c18-8283-43b3-bc51-3e8ea1eed1d5)|
| F3  | ![F3](Figures/Fault-Trees/F3.png)  | [Log](https://review.px4.io/plot_app?log=ddc44231-d83b-4dbf-bc19-cf36f563bd7d)|
| F4  | ![F4](Figures/Fault-Trees/F4.png)  |  [Log](https://review.px4.io/3d?log=5d24b444-67b3-4a1b-8b8e-4b0a33ed2087) |
| F5  | ![F5](Figures/Fault-Trees/F5.png)  |  [Log](https://review.px4.io/3d?log=cf178699-9752-496d-9fb0-620cb414b551)|
| F6  | ![F6](Figures/Fault-Trees/F6.png)  |  [Log](https://review.px4.io/3d?log=ddb05bd2-1399-4d73-8f6f-cd0de7f31f71)|
| F7  | ![F7](Figures/Fault-Trees/F7.png)  |  [Log](https://review.px4.io/3d?log=e70e95d9-69a5-466c-90e3-9bc5eae1bd11)|
| F8  | ![F8](Figures/Fault-Trees/F8.png)  |  [Log](https://review.px4.io/plot_app?log=38ea9f58-42b0-499c-b5e9-edd4e8fee263)|
| F9  | ![F9](Figures/Fault-Trees/F9.png)  | [Log](https://review.px4.io/3d?log=fde5c8d5-f294-47b6-b787-4779a6dfe02e)|
| F10 | ![F10](Figures/Fault-Trees/F10.png) | [Log](https://review.px4.io/3d?log=fde282d7-f051-47b7-9b60-4936cf85c0f9)|
| F11 | ![F11](Figures/Fault-Trees/F11.png) |  [Log](https://review.px4.io/plot_app?log=a09b7c15-5525-494e-9b03-94f17b6ae818)|  

