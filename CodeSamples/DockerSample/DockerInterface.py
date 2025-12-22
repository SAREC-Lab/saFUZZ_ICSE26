import subprocess
import paho.mqtt.client as mqtt
import time
import os
import signal
import xml.etree.ElementTree as ET
import textwrap


# ————————————————————————————————————————————————
# CONSTANTS & XML SNIPPETS
# ————————————————————————————————————————————————
PX4_CID       = "anon"
TY_SDF        = "anon"
GPS_SDF       = "anon"
TMP_TY        = "/tmp/anon.sdf"
TMP_GPS       = "/tmp/gps.sdf"

EX_IMU = textwrap.dedent("""
  <plugin name="gazebo_imu_plugin" filename="libgazebo_imu_plugin.so">
    <robotNamespace></robotNamespace>
    <linkName>anon/imu_link</linkName>
    <imuTopic>/imu</imuTopic>
    <gyroscopeNoiseDensity>0.0003394</gyroscopeNoiseDensity>
    <gyroscopeRandomWalk>3.8785e-05</gyroscopeRandomWalk>
    <gyroscopeBiasCorrelationTime>1000.0</gyroscopeBiasCorrelationTime>
    <gyroscopeTurnOnBiasSigma>0.0087</gyroscopeTurnOnBiasSigma>
    <accelerometerNoiseDensity>0.004</accelerometerNoiseDensity>
    <accelerometerRandomWalk>0.006</accelerometerRandomWalk>
    <accelerometerBiasCorrelationTime>300.0</accelerometerBiasCorrelationTime>
    <accelerometerTurnOnBiasSigma>0.196</accelerometerTurnOnBiasSigma>
  </plugin>
""")

EX_MAG = textwrap.dedent("""
  <plugin name="magnetometer_plugin" filename="libgazebo_magnetometer_plugin.so">
    <robotNamespace />
    <pubRate>100</pubRate>
    <noiseDensity>0.0004</noiseDensity>
    <randomWalk>6.4e-06</randomWalk>
    <biasCorrelationTime>600</biasCorrelationTime>
    <magTopic>/mag</magTopic>
  </plugin>
""")

EX_GPS = textwrap.dedent("""
  <plugin name="gps_plugin" filename="libgazebo_gps_plugin.so">
    <robotNamespace></robotNamespace>
    <gpsNoise>true</gpsNoise>
    <gpsXYRandomWalk>50.0</gpsXYRandomWalk>
    <gpsZRandomWalk>80.0</gpsZRandomWalk>
    <gpsXYNoiseDensity>10.0</gpsXYNoiseDensity>
    <gpsZNoiseDensity>10.0</gpsZNoiseDensity>
    <gpsVXYNoiseDensity>10.0</gpsVXYNoiseDensity>
    <gpsVZNoiseDensity>10.5</gpsVZNoiseDensity>
  </plugin>
""")



# ————————————————————————————————————————————————
# PATCHING LOGIC
# ————————————————————————————————————————————————
def _run(cmd):
    subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def _copy_from(cid, src, dst):
    _run(f"docker cp {cid}:{src} {dst}")

def _copy_to  (cid, src, dst):
    _run(f"docker cp {src} {cid}:{dst}")

def _patch_sdf(path, plugin_name, new_xml, parent_xpath=None):
    tree = ET.parse(path)
    root = tree.getroot()

    # determine parent nodes
    if parent_xpath:
        parents = root.findall(parent_xpath)
    else:
        # default: the first <model> element
        parents = [root.find('model')]

    for parent in parents:
        # remove existing
        for p in parent.findall(f"plugin[@name='{plugin_name}']"):
            parent.remove(p)
        # append the replacement
        parent.append(ET.fromstring(new_xml))

    tree.write(path, encoding='utf-8', xml_declaration=True)

class Docker_Interface:
    def __init__(self, mqtt_client=None,uav_id=None):
        # bash command to start the state machine
        self.uav_id = uav_id 
        self.state_machine_start = f"anon_command"
        self.dev_image_id = "anon"
        self.px4_image_id = "anon"
        self.anon_id = "anon"
        self.anon = self.get_container_name_by_image_id(self.anon_id)
        # initialize process to None
        self.process = None
        # get container name to use
        self.state_machine_container = self.get_container_name_by_image_id(self.dev_image_id)
        self.px4_container = self.get_container_name_by_image_id(self.px4_image_id)
        # MQTT client instance
        self.mqtt_client = mqtt_client

    def get_container_name_by_image_id(self, image_id):
        """Retrieve the container ID for a given image ID."""
        try:
            command = f"docker ps --filter ancestor={image_id} --format '{{{{.ID}}}}'"
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, text=True)
            container_name = result.stdout.strip()
            if container_name:
                return container_name
            else:
                print("[docker_interface] No running containers found for the given image ID.")
                return None
        except subprocess.CalledProcessError as e:
            print(f"[docker_interface] Failed to execute docker command: {e}")
            return None

    def start_px4(self):
        """Start the PX4 container."""
        command = f"docker start {self.px4_container}"
        result = os.system(command)
        if result == 0:
            print(f"[docker_interface] Started PX4 container {self.px4_container}")
        else:
            print(f"[docker_interface] Failed to start PX4 container {self.px4_container}")

    def restart_anon(self):
        """Start the PX4 container."""
        command = f"docker restart {self.anon}"
        result = os.system(command)
        if result == 0:
            print(f"[docker_interface] Started anon container {self.anon}")
        else:
            print(f"[docker_interface] Failed to start anon container {self.anon}")

    def stop_px4(self):
        """Stop the PX4 container."""
        command = f"docker stop {self.px4_container}"
        result = os.system(command)
        if result == 0:
            print(f"[docker_interface] Stopped PX4 container {self.px4_container}")
        else:
            print(f"[docker_interface] Failed to stop PX4 container {self.px4_container}")


    def spawn_state_machine(self):
        command = ["docker", "exec", self.state_machine_container, "/bin/bash", "-c", self.state_machine_start]
        self.process = subprocess.Popen(command, preexec_fn=os.setpgrp,stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.process

    def abort_mission(self):
        self.mqtt_client.publish("ANON", "Shutdown",qos=1)
        unique_pattern = f"anon.py _uav_name:={self.uav_id}"
        kill_command = ["docker", "exec", self.state_machine_container, "pkill", "-f", unique_pattern]
        try:
            subprocess.run(kill_command, check=True)
            print('[docker_interface] State machine process killed successfully.')
        except subprocess.CalledProcessError as e:
            if e.returncode == 1:
                print('[docker_interface] No process found to kill.')
            else:
                print(f'[docker_interface] Error while killing the process: {e}')
        self.stop_px4()
        self.restart_anon()
        self.start_px4()
    
    def get_latest_ulg_file(self):
        """Get the full path of the most recently written .ulg file in the latest log directory."""
        try:
            # Command to find the full path of the most recent .ulg file
            command = (
                f"docker exec {self.px4_container} /bin/bash -c "
                f"'cd /home/user/Firmware/build/px4_sitl_default/logs/ && "
                f"latest_dir=$(ls -td -- */ | head -n 1) && "
                f"cd $latest_dir && "
                f"latest_file=$(ls -t *.ulg | head -n 1) && "
                f"echo $latest_dir$latest_file'"
            )
            # Run the command and capture the output
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            latest_ulg_file_path = result.stdout.strip()
            return latest_ulg_file_path
        except subprocess.CalledProcessError as e:
            print(f"[docker_interface] Failed to get the latest .ulg file path: {e.stderr}")
            return None

    def run_onboard(self):
        self.process = self.spawn_state_machine()
        process_pid = os.getpgid(self.process.pid)
        print('[docker_interface] state machine process started with PID:', process_pid)


    def fuzz_imu (self):
        _copy_from(self.px4_container, TY_SDF, TMP_TY)
        _patch_sdf(   TMP_TY, 'gazebo_imu_plugin',   FUZZ_IMU)
        _copy_to(  self.px4_container, TMP_TY, TY_SDF)
        print("→ IMU fuzzed")

    def reset_imu(self):
        _copy_from(self.px4_container, TY_SDF, TMP_TY)
        _patch_sdf(   TMP_TY, 'gazebo_imu_plugin', DEFAULT_IMU)
        _copy_to(  self.px4_container, TMP_TY, TY_SDF)
        print("→ IMU reset")

    # Magnetometer
    def fuzz_mag (self,level:int):
        _copy_from(self.px4_container, TY_SDF, TMP_TY)
        if level == 0:
            plugin_xml = DEFAULT_MAG
            print("→ Mag reset to default")
        else:
            plugin_xml=MAG_FUZZ_LEVELS[level]
            print(f"→ Mag fuzzed at level {level}")
        _patch_sdf(   TMP_TY, 'magnetometer_plugin',   plugin_xml)
        _copy_to(  self.px4_container, TMP_TY, TY_SDF)
        

    def reset_mag(self):
        _copy_from(self.px4_container, TY_SDF, TMP_TY)
        _patch_sdf(   TMP_TY, 'magnetometer_plugin', DEFAULT_MAG)
        _copy_to(  self.px4_container, TMP_TY, TY_SDF)
        print("→ Mag reset")

    # GPS (in gps.sdf, under sensor)
    def fuzz_gps (self,level:int):
        _copy_from(self.px4_container, GPS_SDF, TMP_GPS)
        if level == 0:
            plugin_xml=DEFAULT_GPS
        else:
            plugin_xml = GPS_FUZZ_LEVELS[level]
            print(f"→ GPS fuzzed at level {level}")
        _patch_sdf(TMP_GPS, 'gps_plugin',   plugin_xml,
                      parent_xpath=".//sensor[@name='gps']")
        _copy_to(  self.px4_container, TMP_GPS, GPS_SDF)

    def reset_gps(self):
        _copy_from(self.px4_container, GPS_SDF, TMP_GPS)
        _patch_sdf(   TMP_GPS, 'gps_plugin', DEFAULT_GPS,
                      parent_xpath=".//sensor[@name='gps']")
        _copy_to(  self.px4_container, TMP_GPS, GPS_SDF)
        print("→ GPS reset")

    def deploy_default_world(self):
        """Push the pristine default.world into the PX4 container."""
        cmd = [
            'docker', 'cp',
            os.path.abspath(LOCAL_DEFAULT_WORLD),
            f'{self.px4_container}:{REMOTE_WORLD_PATH}'
        ]
        subprocess.run(cmd, check=True)
        print(f"→ Restored clean world from {LOCAL_DEFAULT_WORLD}")

    def deploy_windy_world(self):
        """Push the pre‐built windy.world (with wind_plugin) into the PX4 container."""
        cmd = [
            'docker', 'cp',
            os.path.abspath(LOCAL_WINDY_WORLD),
            f'{self.px4_container}:{REMOTE_WORLD_PATH}'
        ]
        subprocess.run(cmd, check=True)
        print(f"→ Injected windy world from {LOCAL_WINDY_WORLD}")

