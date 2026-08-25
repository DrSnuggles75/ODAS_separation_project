from launch import LaunchDescription
from launch_ros.actions import Node

_N_SOURCES = 4


def _split(name, in_topic):
    """One split_channel_node: N-channel interleaved AudioFrame -> N mono topics."""
    return Node(
        package='audio_utils',
        executable='split_channel_node.py',
        name=name,
        parameters=[{
            'input_format': 'signed_16',
            'output_format': 'signed_16',
            'channel_count': _N_SOURCES,
        }],
        remappings=[('audio_in', in_topic)]
        + [(f'audio_out_{i}', f'{in_topic}/source_{i}') for i in range(_N_SOURCES)],
    )


def generate_launch_description():
    # Split the raw separated stream, and the postfiltered stream (/sss_pf) once the
    # Pi bridge publishes it. The sss_pf split is harmless if /sss_pf is never published.
    return LaunchDescription([
        _split('sss_split_channel', 'sss'),
        _split('sss_pf_split_channel', 'sss_pf'),
    ])
