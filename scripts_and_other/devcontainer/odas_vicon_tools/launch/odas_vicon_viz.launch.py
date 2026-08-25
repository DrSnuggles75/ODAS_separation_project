from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('vicon_hostname', default_value='192.168.50.143'),
        DeclareLaunchArgument('world_frame', default_value='vicon_world'),
        DeclareLaunchArgument('rviz', default_value='true'),

        Node(
            package='vicon_receiver',
            executable='vicon_client',
            name='vicon_client',
            output='screen',
            parameters=[{
                'hostname': LaunchConfiguration('vicon_hostname'),
                'buffer_size': 200,
                'namespace': 'vicon',
            }],
        ),

        Node(
            package='odas_vicon_tools',
            executable='vicon_tf_bridge',
            name='vicon_tf_bridge',
            output='screen',
            parameters=[{
                'world_frame': LaunchConfiguration('world_frame'),
                'vicon_namespace': 'vicon',
                # 'segments' left at its node default (['box_mic']).
            }],
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', PathJoinSubstitution([
                FindPackageShare('odas_vicon_tools'), 'config', 'odas_vicon.rviz'
            ])],
            condition=IfCondition(LaunchConfiguration('rviz')),
        ),
    ])
