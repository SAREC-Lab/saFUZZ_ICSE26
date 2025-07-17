# Behavioral Fuzzing for Mode Transitions and Failsafes in sUAS

![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Overview

SAFUS is an automated fuzz testing pipeline designed to validate the autonomous behavior of small Uncrewed Aerial Systems (sUAS). By targeting mode transitions and failsafe mechanisms in layered sUAS state machines, SAFUS exposes subtle failures that may arise due to environmental disturbances, timing variability, and human interaction.

This framework enhances safety assurance by systematically generating fuzz scenarios, executing tests in simulation and physical platforms, and producing fault trees to aid root cause analysis.

---

## Features

- **Layered state machine analysis** covering application-level logic and autopilot firmware (PX4, ArduPilot).  
- **Semantic fuzzing pipeline** injecting realistic environmental and timing disturbances.  
- **Automated generation** of test scenarios from hazard analysis.  
- **Decision-tree based labeling** to classify test outcomes (success, failure, invalid).  
- **Fault tree visualization** for failure root cause investigation.  
- **Support for simulation-based and real-world testing** of autonomous sUAS.  

---

## Motivation

Autonomous sUAS operate in unpredictable environments and rely on complex state machines for safe and reliable behavior. Existing testing approaches often focus on low-level input mutations or specific functionalities but lack systematic validation of cross-layer state transitions and failsafe activations under realistic conditions.

SAFUS fills this gap by enabling behaviorally meaningful fuzz testing to detect critical faults early in development.

---

## Architecture

The SAFUS pipeline consists of two main phases:

1. **Hazard Analysis & Test Specification**  
   - Identify relevant hazards related to mode transitions, failsafes, and human controls.  
   - Define fuzz scenario templates specifying states, modes, environment conditions, and control inputs.

2. **Automated Test Execution & Analysis**  
   - Generate and run tests in a high-fidelity simulation environment.  
   - Monitor system responses and classify outcomes using decision trees.  
   - Cluster failure cases for anomaly detection.  
   - Generate fault trees highlighting root causes.
   - 
*Figure: High-level SAFUS pipeline architecture.*
