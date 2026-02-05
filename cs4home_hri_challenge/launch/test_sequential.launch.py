import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    namespace = LaunchConfiguration('namespace')
    pkg_dir = get_package_share_directory('cs4home_hri_challenge')
    params_file = os.path.join(pkg_dir, 'config', 'test_params.yaml')

    declare_namespace_cmd = DeclareLaunchArgument(
        'namespace',
        default_value='',
        description='Namespace')

    greeting_guest_node = Node(
        package='cs4home_hri_challenge',
        executable='greeting_guest_cognitive_module',
        name='greeting_guest_cognitive_module',
        namespace=namespace,
        output='screen',
        parameters=[params_file]
    )

    describe_person_node = Node(
        package='cs4home_hri_challenge',
        executable='describe_person_cognitive_module',
        name='describe_person_cognitive_module',
        namespace=namespace,
        output='screen',
        parameters=[params_file]
    )

    find_seat_node = Node(
        package='cs4home_hri_challenge',
        executable='find_seat_cognitive_module',
        name='find_seat_cognitive_module',
        namespace=namespace,
        output='screen',
        parameters=[params_file]
    )

    hri_challenge_master = Node(
        package='cs4home_hri_challenge',
        executable='hri_challenge_master',
        name='hri_challenge_master',
        namespace=namespace,
        output='screen',
        parameters=[params_file]
    )

    ld = LaunchDescription()
    ld.add_action(declare_namespace_cmd)
    ld.add_action(hri_challenge_master)
    ld.add_action(greeting_guest_node)
    ld.add_action(describe_person_node)
    ld.add_action(find_seat_node)
    return ld
