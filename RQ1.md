## RQ1: To what extent can test oracle functionality be automated for autonomous sUAS fuzz testing in a real-world system?


We used the following three Fuzz Scenario Templates (FSTs) to automate the test oracle functionality for autonomous sUAS fuzz testing:

## Fuzz Scenario Templates

<a name="scenarios"></a>

| **Fuzz Scenario** | **FSC-1** | **FSC-2** | **FSC-3** |
|-------------------|-----------|-----------|-----------|
| **Overview** | Test human control across multiple states | Test Failsafe actions across two states | Test Failsafe actions triggered by geofence |
| **JSON Specification** | [FSC1.json](Listings/FSC1.json) | [FSC2.json](Listings/FSC2.json) | [FSC3.json](Listings/FSC3.json) |
| **PX4 Modes** | `OFFBOARD`, `LAND` | `OFFBOARD` | `OFFBOARD` |
| **Tested App States** | `TAKEOFF`, `FLYING_TO_WAYPOINT`, `HOVERING`, `LANDING`, `DISARMING` | `FLYING_TO_WAYPOINT`, `HOVERING` | `FLYING_TO_WAYPOINT` |
| **Tested Mode activations** | *RC_INPUT:* `ALTCTL`, `POSCTL`, `STABILIZED` | *RC_INPUT:* `AUTO.LOITER`, `AUTO.LAND`, `AUTO.RTL` | *GEOFENCE ACTIONS:* RTL (+LAND), LAND, WARNING<br>*RC_INPUT_EVENTS:* `ALTCTL`, `POSCTL`, `STABILIZED` |
| **Environment / Context** | - *Delay:* short (50–200), medium (200–600), long (600–1200) ms<br>- *Throttle:* mid<br>- *Geofence:* none<br>- *Wind, GPS, Compass:* none<br>- *Context:* Flight plan A<br>- *Constraints:* PX4 mode -- App state mapping | - *Delay:* short / medium<br>- *Throttle:* mid<br>- *Geofence:* none<br>- *Wind, GPS, Compass:* none &#124; low / medium / high &#124; low / medium / high<br>- *Context:* Flight plan B | - *Delay:* short / medium / long<br>- *Throttle:* mid<br>- *Geofence:* active &#124; actions: `WARN`, `RETURN`, `TERMINATE`<br>- *Wind, GPS, Compass:* none<br>- *Context:* Flight plan C |
| **Failures** |  |  |  |


<br><br><br>



## Decision Tree for Test Oracle Automation
<a name="decision-tree"></a>
![Decision Tree for Test Oracle Automation](Figures/decision_tree.png)
