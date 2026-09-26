# cs4home_hri_challenge

This repository implements the CoreSense4Home HRI Challenge. It coordinates cognitive modules for receiving a guest, describing and introducing the person, finding a seat, and assisting with a bag.

## CoreSense role

The terms below follow the [CoreSense Ontology (CSO)](https://w3id.org/coresense/cso).

- The HRI Challenge is a [Functionality](https://w3id.org/coresense/cso#Functionality) exercised in a domestic social context.
- Dialogue, person perception, guest description, seating and bag assistance are [Cognitive Capabilities](https://w3id.org/coresense/cso#CognitiveCapability).
- The robot is the [Agent](https://w3id.org/coresense/cso#Agent) coordinating the interaction.
- Each challenge flow is a [Task](https://w3id.org/coresense/cso#Task) made of planned [Actions](https://w3id.org/coresense/cso#Action).
- The [Goal](https://w3id.org/coresense/cso#Goal) is a desired social state in which the guest has been received and assisted.

## Task flow

~~~mermaid
flowchart TD
    start["Guest arrives"] --> greet["Greet guest"]
    greet --> master{"HRI challenge flow"}
    master --> describe["Describe person"]
    describe --> seat1["Find seat"]
    master --> bag["Receive bag"]
    bag --> introduce["Introduce guest"]
    introduce --> seat2["Find seat"]
    seat2 --> transport["Transport bag"]
    seat1 --> goal["Guest assisted"]
    transport --> goal
~~~

The `hri_challenge_master` selects and coordinates the configured flow while each stage executes its behaviour tree.

## Requirements

Use Ubuntu 22.04 and ROS 2 Humble. The full task uses the CoreSense4Home perception, dialogue, navigation and manipulation systems.

## Build

~~~bash
mkdir -p ~/robocup24_ws/src
cd ~/robocup24_ws/src
git clone https://github.com/CoreSenseEU/cs4home_hri_challenge.git
vcs import --recursive < cs4home_hri_challenge/thirdparty.repos
cd ..
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
~~~

## Run

Start the CoreSense4Home perception, dialogue, navigation and manipulation dependencies required by the selected scenario. Then launch the challenge modules:

~~~bash
ros2 launch cs4home_hri_challenge hri_challenge.launch.py
~~~

## Acknowledgement

<img src="https://github.com/user-attachments/assets/b11da974-9201-4f79-902e-c9c20e8aa7a4" alt="Funded by the European Union" width="240"/>

This work has received funding from the European Union's Horizon Europe research and innovation programme under grant agreement No 101070254 ([CORESENSE](https://coresense.eu)). Views and opinions expressed are however those of the author(s) only and do not necessarily reflect those of the European Union or the European Commission. Neither the European Union nor the granting authority can be held responsible for them.
