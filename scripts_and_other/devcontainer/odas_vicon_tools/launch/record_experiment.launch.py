import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.substitutions import LaunchConfiguration

DEFAULT_BAG_DIR = os.path.expanduser('~/experiments/odas_vicon_bags')

DEFAULT_TOPICS_REGEX = (
    r'^/ssl$|^/sst$|^/sst_poses$|^/ssl_pcl2$|^/sss$|^/sss/source_\d+$|^/tf$|^/tf_static$|^/vicon/.*'
)


def _start_recording(context, *args, **kwargs):
    bag_dir = LaunchConfiguration('bag_dir').perform(context)
    topics_regex = LaunchConfiguration('topics_regex').perform(context)
    os.makedirs(bag_dir, exist_ok=True)
    return [
        ExecuteProcess(
            cmd=['ros2', 'bag', 'record', '--regex', topics_regex],
            cwd=bag_dir,
            output='screen',
        )
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'bag_dir',
            default_value=DEFAULT_BAG_DIR,
            description='Directory under which a timestamped rosbag2 folder is created for this run.',
        ),
        DeclareLaunchArgument(
            'topics_regex',
            default_value=DEFAULT_TOPICS_REGEX,
            description='Regex passed to `ros2 bag record --regex` selecting which topics to capture.',
        ),
        OpaqueFunction(function=_start_recording),
    ])
