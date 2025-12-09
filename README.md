# cs4home_recepcionist

Receptionist cognitive module for the CoreSense4Home (RoboCup @Home) stack. It orchestrates the greeting of a person at the entrance of the house, inviting them inside and offering them a seat. It also provides voice feedback via TTS. The launch file starts:
- greeting_guest_cognitive_module (this package)
- audio player (audio_common)
- text-to-speech node (tts_ros)

## 1. Prerequisites
- Ubuntu 22.04 + ROS 2 Humble installed and sourced
- colcon + rosdep + vcs tools installed
- Working CUDA GPU (optional, for faster TTS / future perception)

## 2. Create or reuse a workspace
If you do not already have a RoboCup/CoreSense workspace, create one:
```bash
mkdir -p robocup24_ws/src
cd robocup24_ws/src
```

## 3. Clone core stack 
Clone the  repository 
```bash
git clone https://github.com/CoreSenseEU/cs4home_receptionist.git
```

## 4. Import third‑party repositories
This package ships a `thirdparty.repos` manifest you can feed into `vcs` to pull additional sources:
```bash
vcs import --recursive < cs4home_receptionist/thirdparty.repos
```

## 5. Install system & ROS package dependencies
From the workspace root:
```bash
cd ..   # ensure you are at robocup24_ws level (one above src)
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```
Run rosdep again later if you add more packages.
## 6. Install [Perception System](https://github.com/jmguerreroh/perception_system)


## 7. Install [Whisper](https://github.com/mgonzs13/whisper_ros)


## 8. Build
```bash
colcon build --symlink-install
```

## 9. Source the overlay
```bash
source install/setup.bash
```
Add the above line to your shell rc file for convenience.

## 10. Launch receptionist

Launch dependencies
```bash
ros2 launch robocup_bringup receptionist_dependencies.launch.py
```
Launch receptionist
```bash
ros2 launch cs4home_receptionist receptionist.launch.py
```


