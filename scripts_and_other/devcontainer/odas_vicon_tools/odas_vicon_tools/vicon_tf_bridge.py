#!/usr/bin/env python3
import re

import rclpy
from rclpy.node import Node
from vicon_receiver.msg import Position
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster

POSITION_TYPE = 'vicon_receiver/msg/Position'


class ViconTfBridge(Node):
    """Broadcasts TF for every Vicon-tracked segment it discovers, since vicon_receiver only publishes Position topics."""

    def __init__(self):
        super().__init__('vicon_tf_bridge')

        self.declare_parameter('world_frame', 'vicon_world')
        self.declare_parameter('vicon_namespace', 'vicon')
        self.declare_parameter('discovery_period_sec', 2.0)

        self.world_frame = self.get_parameter('world_frame').get_parameter_value().string_value
        namespace = self.get_parameter('vicon_namespace').get_parameter_value().string_value
        discovery_period = self.get_parameter('discovery_period_sec').get_parameter_value().double_value

        self._topic_pattern = re.compile(rf'^/{re.escape(namespace)}/([^/]+)/([^/]+)$')
        self._bridged_topics = set()

        self.broadcaster = TransformBroadcaster(self)
        self._subs = []

        self._discover_topics()
        self.create_timer(discovery_period, self._discover_topics)

    def _discover_topics(self):
        for topic_name, types in self.get_topic_names_and_types():
            if topic_name in self._bridged_topics or POSITION_TYPE not in types:
                continue
            match = self._topic_pattern.match(topic_name)
            if not match:
                continue
            segment = match.group(2)
            self._bridged_topics.add(topic_name)
            self._subs.append(
                self.create_subscription(Position, topic_name, self._make_callback(segment), 10)
            )
            self.get_logger().info(f'Discovered Vicon object: bridging {topic_name} -> TF {self.world_frame} -> {segment}')

    def _make_callback(self, child_frame):
        def callback(msg: Position):
            t = TransformStamped()
            t.header.stamp = self.get_clock().now().to_msg()
            t.header.frame_id = self.world_frame
            t.child_frame_id = child_frame
            # Position.msg gives translation in mm.
            t.transform.translation.x = msg.x_trans / 1000.0
            t.transform.translation.y = msg.y_trans / 1000.0
            t.transform.translation.z = msg.z_trans / 1000.0
            t.transform.rotation.x = msg.x_rot
            t.transform.rotation.y = msg.y_rot
            t.transform.rotation.z = msg.z_rot
            t.transform.rotation.w = msg.w
            self.broadcaster.sendTransform(t)
        return callback


def main(args=None):
    rclpy.init(args=args)
    node = ViconTfBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
