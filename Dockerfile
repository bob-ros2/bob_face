# Use ROS Humble as the base image
ARG ROS_DISTRO=humble
FROM ros:${ROS_DISTRO}-ros-base

# Set the workspace directory
ENV ROS_WS=/ros2_ws
WORKDIR ${ROS_WS}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    python3-pip \
    python3-pyqt5 \
    ros-${ROS_DISTRO}-visualization-msgs \
    ros-${ROS_DISTRO}-std-msgs \
    ros-${ROS_DISTRO}-rosbag2-cpp \
    # PyQt5 and GUI dependencies (needed for face_gui.py)
    libqt5gui5 \
    && rm -rf /var/lib/apt/lists/*

# Clone dependencies
RUN git clone https://github.com/bob-ros2/bob_msgs src/bob_msgs && \
    git clone https://github.com/bob-ros2/bob_launch src/bob_launch

# Copy the requirements file and install Python dependencies
COPY requirements.txt src/bob_face/requirements.txt
RUN pip3 install --no-cache-dir -r src/bob_face/requirements.txt

# Copy the bob_face source code
COPY . src/bob_face/

# Build the workspace and cleanup to save space
RUN . /opt/ros/${ROS_DISTRO}/setup.sh && \
    colcon build --packages-up-to bob_face bob_launch && \
    rm -rf build/ log/

# Setup the environment for interactive shells
RUN echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /etc/bash.bashrc && \
    echo "source ${ROS_WS}/install/setup.bash" >> /etc/bash.bashrc

# ENTRYPOINT sources ROS and workspace setup
ENTRYPOINT ["/bin/bash", "-c", "source /opt/ros/$ROS_DISTRO/setup.bash && source $ROS_WS/install/setup.bash && exec \"$@\"", "bash"]

# Default command if no arguments are provided
CMD ["bash"]
