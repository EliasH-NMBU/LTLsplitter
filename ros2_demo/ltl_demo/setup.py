import glob

from setuptools import find_packages, setup

package_name = 'ltl_demo'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob.glob('launch/*.launch.py')),
        ('share/' + package_name + '/worlds', glob.glob('worlds/*.sdf')),
        ('share/' + package_name + '/urdf', glob.glob('urdf/*.xacro')),
    ],
    package_data={'': ['py.typed']},
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Elias Evjen Hartmark',
    maintainer_email='elias.hartmark@gmail.com',
    description='LTLsplitter ROS2 demo: TurtleBot3 in Gazebo with human detection and a safety-stop override, monitored by an Ogma-generated LTL monitor.',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'detector = ltl_demo.detector:main',
            'wander = ltl_demo.wander:main',
            'human_blinker = ltl_demo.human_blinker:main',
        ],
    },
)
