import os
from glob import glob

from setuptools import setup

package_name = 'odas_vicon_tools'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.rviz')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='oscar',
    maintainer_email='oscar.fahlen@gmail.com',
    description='Vicon-to-TF bridge and RViz setup for overlaying ODAS source tracking on Vicon ground truth.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'vicon_tf_bridge = odas_vicon_tools.vicon_tf_bridge:main',
            'capture_sss = odas_vicon_tools.capture_sss:main',
            'sst_monitor = odas_vicon_tools.sst_monitor:main',
            'sst_target = odas_vicon_tools.sst_target:main',
        ],
    },
)
