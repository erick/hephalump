import paramiko
import subprocess
import time
from utils import Result


class BGPHVirtualMachine:
    def __init__(self) -> None:
        self.SSH_PORT_FORWARDING=8022
        self.hostname = "localhost"
        self.port = self.SSH_PORT_FORWARDING
        self.username = "mininet"
        self.password = "mininet"
        self.guest_submission_path = "/autograder/submission/"
        self.BGPH_path = "/autograder/submission/BGPHijacking"
        self.topology_start_output = ""

        self.ssh_client = None

    def start_vm(self):
        # Define the QEMU command and parameters
        qemu_command = [
            "qemu-system-x86_64",  # QEMU binary
            "-m", "1024",  # Memory allocation in MB
            "-nographic",  # Run without a graphical interface
            "/autograder/source/mininet-vm-x86_64.vmdk",  # Path to the VMDK file
            "-net", "nic,model=virtio",  # Network interface configuration
            "-net", f"user,net=192.168.101.0/24,hostfwd=tcp::{self.SSH_PORT_FORWARDING}-:22",  # User-mode networking with port forwarding
            "-virtfs", "local,id=hostshare,path=/autograder/submission,mount_tag=submission,security_model=none",
        ]

        try:
            # detatch
            subprocess.Popen(qemu_command, start_new_session=True)
        except subprocess.CalledProcessError as e:
            print(f"An error occurred while running QEMU: {e}")
            return False
        except FileNotFoundError:
            print("QEMU is not installed or not found in the system path.")
            return False
        return True


    def _attempt_ssh_connection(self, hostname: str, port: int, username: str, password: str,
                               connection_timeout_sec: int):
        try:
            # Create a new SSH client
            ssh_client = paramiko.SSHClient()

            # Load system host keys and set policy for missing host keys
            ssh_client.load_system_host_keys()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect to the server with a timeout
            ssh_client.connect(hostname, port=port, username=username, password=password, timeout=connection_timeout_sec)
            print(f"Successfully connected to {hostname}:{port}")
            return ssh_client
        except paramiko.SSHException as e:
            print(f"SSH connection error: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")

        return None

    def get_ssh_terminal(self):
        # Retry configuration
        max_retries = 20
        retry_interval = 10  # seconds
        connection_timeout_sec = 3  # seconds

        ssh_client = None
        for attempt in range(max_retries):
            print(f"Attempt {attempt + 1}/{max_retries}")
            ssh_client = self._attempt_ssh_connection(
                self.hostname, self.port, self.username, self.password, connection_timeout_sec)
            if ssh_client:
                break
            time.sleep(retry_interval)  # Wait before the next attempt
        else:
            print("Max attempts reached. Unable to connect.")

        return ssh_client

    def shutdown(self):
        print("Shutting down mininet VM")
        ssh_client = self.get_ssh_terminal()
        if not ssh_client:
            return
        ssh_client.exec_command("sudo shutdown now")
        ssh_client.close()

    def init(self):
        print("Initializing mininet VM")
        self.ssh_client = self.get_ssh_terminal()
        if not self.ssh_client:
            return False
        _, stdout, std_err = self.ssh_client.exec_command(f"sudo mkdir -p {self.guest_submission_path}")
        _, stdout, std_err = self.ssh_client.exec_command(f"sudo mount -t 9p -o trans=virtio submission {self.guest_submission_path}")

        # setup permissions
        time.sleep(1)
        self.ssh_client.exec_command(f"cd {self.BGPH_path} && chmod +x *.sh")
        _, stdout, std_err = self.ssh_client.exec_command(f"ls -al {self.BGPH_path}")
        print(f"Files in {self.BGPH_path}: {stdout.read().decode()}")
        return self.ssh_client

    def send_cmd(self, shell, cmd: str, sleep_sec=2):
        shell.send(cmd)
        time.sleep(sleep_sec)

    def start_topology(self, shell) -> Result:
        print("Starting topology")
        self.send_cmd(shell, f"cd {self.BGPH_path} && sudo python3 bgp.py\n", 30)
        output = ""
        output += shell.recv(2048).decode()

        print("Waiting for topology to start")
        MAX_RETRIES = 5
        while "*** Starting CLI:" not in output:
            output += shell.recv(2048).decode()
            time.sleep(5)
            MAX_RETRIES -= 1
            if MAX_RETRIES < 0:
                return Result(False, "Topology did not start, please check bgp.py")

        print(output)
        self.topology_start_output = output
        return Result(True)

    def get_topology_start_output(self):
        return self.topology_start_output

    def stop_topology(self, shell):
        """
        Must use the same shell as start_topology
        """
        self.send_cmd(shell, "exit\n", 5)

    def start_rogue(self, use_hard=False) -> Result:
        print("Starting rogue server")

        if not use_hard:
            cmd = f"cd {self.BGPH_path} && bash ./start_rogue.sh"
        else:
            cmd = f"cd {self.BGPH_path} && bash ./start_rogue_hard.sh"

        if not self.ssh_client:
            return Result(False, "SSH client not initialized")
        _, std_out, std_err = self.ssh_client.exec_command(cmd)
        return_code = std_out.channel.recv_exit_status()
        if return_code != 0:
            return Result(False, std_err.read().decode())
        time.sleep(5)
        return Result(True)

    def stop_rogue(self):
        print("Stopping rogue server")
        if not self.ssh_client:
            return Result(False, "SSH client not initialized")
        _, std_out, std_err = self.ssh_client.exec_command(f"cd {self.BGPH_path} && bash ./stop_rogue.sh")

        return_code = std_out.channel.recv_exit_status()
        if return_code != 0:
            return Result(False, std_err.read().decode())

        time.sleep(5)
        return Result(True)

    def check_website(self, shell, host="h5-1") -> str:
        self.send_cmd(shell, f"cd {self.BGPH_path} && bash ./website.sh {host}\n", 10)
        self.send_cmd(shell, f"{chr(3)}\n") # ctrl+c
        output = shell.recv(4096).decode()
        return output

    def bgp_messages(self, shell, router="R3") -> str:
        self.send_cmd(shell, f"cd {self.BGPH_path} && bash ./connect.sh {router}\n", 5)
        self.send_cmd(shell, f"en\n", 3) # password
        self.send_cmd(shell, f"sh ip bgp\n", 3) # password
        output = shell.recv(4096).decode()
        return output

