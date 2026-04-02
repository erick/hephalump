import os
import socket
import struct
import time
import subprocess
import hashlib
import paramiko
from utils import Result

class BGPHVirtualMachine:
    def __init__(self) -> None:
        self.topology_start_output = ""
        self.submission_dir = "/autograder/submission/"
        self.BGPHijacking_dir = f"{self.submission_dir}BGPHijacking"
        self.ssh_client = None
        self.hostipv4 = "127.0.0.1"
        self.SSH_FWD_PORT = 8022
        self.username = "mininet"
        self.password = "mininet"
        self.init_complete = False
        self.anti_cheating_secret = hashlib.sha256(f"CS6250{time.time()}666".encode()).hexdigest()[0:16]


    # def _kvm_available(self) -> bool:
    #     """Check if KVM is available on this host"""
    #     return os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)


    def start_vm(self):
        print(f"\n==> BGPHVirtualMachine.start_vm()")

        # use_kvm = self._kvm_available()
        # print(f"KVM available: {use_kvm}")

        # qemu_command = [
        #     "qemu-system-x86_64",  # QEMU binary
        #     "-m", "1536",  # Memory allocation in MB (was 1024)
        #     "-nographic",  # Run without a graphical interface
        #     "-net", "nic,model=virtio",  # Network interface configuration
        #     "-net", f"user,net=192.168.101.0/24,hostfwd=tcp::{self.SSH_FWD_PORT}-:22",  # User-mode networking with port forwarding
        #     "-virtfs", "local,id=hostshare,path=/autograder/submission,mount_tag=submission,security_model=none",
        #     # "-drive", "file=/autograder/source/mininet-vm-x86_64.vmdk,format=vmdk",
        #     "-drive", "file=/autograder/source/mininet-vm-x86_64.qcow2,format=qcow2",
        #     # "/autograder/source/mininet-vm-x86_64.vmdk",  # Path to the VMDK file
        # ]

        # qemu_command = [
        #     "qemu-system-x86_64",  # QEMU binary
        #     "-m", "1536",  # Memory allocation in MB
        #     "-nographic",  # Run without a graphical interface
        #     "-device", "virtio-net-pci,netdev=net0",
        #     "-netdev", f"user,id=net0,net=192.168.101.0/24,hostfwd=tcp::{self.SSH_FWD_PORT}-:22",
        #     "-virtfs", "local,id=hostshare,path=/autograder/submission,mount_tag=submission,security_model=none",
        #     # "-drive", "file=/autograder/source/mininet-vm-x86_64.vmdk,format=vmdk",
        #     "-drive", "file=/autograder/source/mininet-vm-x86_64.qcow2,format=qcow2",
        # ]

        # Create log files in current directory

        qemu_command = [
            "qemu-system-x86_64",  # QEMU binary
            "-m", "1536",  # Memory allocation in MB
            "-display", "none",
            "-serial", "stdio",  # was "none"
            "-monitor", "unix:/tmp/qemu-monitor.sock,server,nowait",
            # "-net", "nic,model=virtio",  # Network interface configuration
            # "-net", f"user,net=192.168.101.0/24,hostfwd=tcp::{self.SSH_FWD_PORT}-:22",  # User-mode networking with port forwarding
            "-device", "virtio-net-pci,netdev=net0",
            "-netdev", f"user,id=net0,net=192.168.101.0/24,hostfwd=tcp::{self.SSH_FWD_PORT}-:22",
            "-virtfs", "local,id=hostshare,path=/autograder/submission,mount_tag=submission,security_model=none",
            "-drive", "file=/autograder/source/mininet-vm-x86_64.qcow2,format=qcow2",
            "-no-reboot",
            "-D", "/tmp/qemu-debug.log", "-d", "guest_errors,unimp",
        ]

        # if use_kvm:
        #     qemu_command.insert(1, "-enable-kvm")

        print(f"QEMU command:\n{' '.join(qemu_command)}")

        # @contextmanager
        # def qemu_logs():
        #     qemu_stdout_log = open("qemu_stdout.log", "ab")
        #     qemu_stderr_log = open("qemu_stderr.log", "ab")
        #     try:
        #         yield qemu_stdout_log, qemu_stderr_log
        #     finally:
        #         qemu_stdout_log.close()
        #         qemu_stderr_log.close()

        try:
            self.qemu_process = subprocess.Popen(
                qemu_command,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        #     with qemu_logs() as (qemu_stdout_log, qemu_stderr_log):
        #         self.qemu_process = subprocess.Popen(
        #             qemu_command,
        #             start_new_session=True,
        #             stdin=subprocess.DEVNULL,
        #             stdout=qemu_stdout_log,
        #             stderr=qemu_stderr_log,
        #         )
        except (OSError, FileNotFoundError) as e:
            print(f"Failed to start QEMU: {e}")
            return False

        # Check QEMU didn't exit immediately (e.g. bad args, missing VMDK)
        time.sleep(3)
        if self.qemu_process.poll() is not None:
            stdout_output = self.qemu_process.stdout.read().decode()
            stderr_output = self.qemu_process.stderr.read().decode()
            print(f"QEMU exited immediately (code {self.qemu_process.returncode})")
            print(f"stdout (serial): {stdout_output}")
            print(f"stderr: {stderr_output}")
            return False

        print(f"     Waiting for the QEMU VM sshd to initialize")

        print(f"     Sleeping for 120s to give the QEMU VM time to boot and sshd to initialize")
        # There is also retry logic in get_ssh_client() that will wait for sshd to initialize
        time.sleep(120)

        print(f"     Waiting for the QEMU VM sshd banner")
        if not self._wait_for_sshd(hostname=self.hostipv4, port=self.SSH_FWD_PORT, total_wait=600, interval=5):
            print("QEMU VM sshd never initialized - exiting")
            return False

        print(f"QEMU network info:\n{self.qemu_monitor_cmd('info network')}")

        return self.init()


    def qemu_monitor_cmd(self, cmd: str) -> str:
        """Send a command to the QEMU monitor via Unix socket."""
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect("/tmp/qemu-monitor.sock")
            s.settimeout(5)
            s.recv(1024)  # consume the "(qemu) " prompt
            s.send((cmd + "\n").encode())
            time.sleep(1)
            response = s.recv(4096).decode()
            s.close()
            return response
        except (OSError, socket.timeout) as e:
            return f"Monitor error: {e}"


    def _attempt_ssh_connection(self, hostname: str = None, port: int = None, username: str = None, password: str = None,
                               timeout: int = 10) -> paramiko.SSHClient:
        print(f"\n==> BGPHVirtualMachine._attempt_ssh_connection()")

        if hostname is None:
            hostname = self.hostipv4
        if port is None:
            port = self.SSH_FWD_PORT
        if username is None:
            username = self.username
        if password is None:
            password = self.password

        try:
            # Create a new SSH client
            ssh_client = paramiko.SSHClient()

            # Load system host keys and set policy for missing host keys
            # ssh_client.load_system_host_keys()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect to the server with a timeout
            # ssh_client.connect(hostname, port=port, username=username, password=password, timeout=connection_timeout_sec)
            ssh_client.connect(
                hostname=hostname,
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                banner_timeout=30,
                auth_timeout=20,
                look_for_keys=False,
                allow_agent=False,
            )
            print(f"Successfully connected to {hostname}:{port}")
            return ssh_client
        except paramiko.SSHException as e:
            print(f"SSH connection error: {e}")
        except (OSError, EOFError, socket.error, ConnectionResetError) as e:
            print(f"Connection error (retryable): {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")


    def get_ssh_client(self):
        print(f"\n==> BGPHVirtualMachine.get_ssh_client()")

        # Retry configuration
        max_retries = 20
        retry_interval = 15  # seconds
        client_connect_timeout = 10  # seconds (increased from 3)

        ssh_client = None
        for attempt in range(max_retries):
            print(f"SSH connection attempt {attempt + 1}/{max_retries}")
            ssh_client = self._attempt_ssh_connection(
                hostname=self.hostipv4, port=self.SSH_FWD_PORT, username=self.username, password=self.password, timeout=client_connect_timeout)
            if ssh_client:
                break
            time.sleep(retry_interval)  # Wait before the next attempt
        else:
            print("Max attempts reached. Unable to connect.")

        return ssh_client


    def _ssh_exec_command(self, cmd: str, show_output: bool = False):
        print(f"\n==> BGPHVirtualMachine._ssh_exec_command()")
        if not self.ssh_client:
            print(f"     > {cmd} -- SSH client not initialized")
            return [-1, "", "SSH client not initialized"]

        try:
            print(f"     > {cmd}", end='')
            _, std_out, std_err = self.ssh_client.exec_command(cmd)
            retcode = std_out.channel.recv_exit_status()
            std_err_txt = std_err.read().decode()
            std_out_txt = std_out.read().decode()
            print(f" ({retcode = })")

            if show_output and std_out_txt:
                print(f"     stdout:\n{std_out_txt}\n")
            if show_output and std_err_txt:
                print(f"     stderr:\n{std_err_txt}\n")
        except paramiko.SSHException as e:
            print(f" -- SSH command execution error: {e}")
            return [-1, "", str(e)]

        return [retcode, std_out_txt, std_err_txt]


    def init(self):
        print(f"\n==> BGPHVirtualMachine.init()")
        self.ssh_client = self.get_ssh_client()

        if not self.ssh_client:
            return False

        if not self.init_complete:
            # mount the submission directory using 9p virtiofs
            ret, out, err = self._ssh_exec_command(f"sudo mkdir -p {self.submission_dir}")
            ret, out, err = self._ssh_exec_command(f"sudo mount -t 9p -o trans=virtio,msize=262144 submission {self.submission_dir}")
            # set permissions for scripts in BGPHijacking dir
            ret, out, err = self._ssh_exec_command(f"cd {self.BGPHijacking_dir} && sudo chmod +x *.sh")
            # create /tmp/anti_cheating_secret5566.txt with the anti-cheating secret
            ret, out, err = self._ssh_exec_command(f"echo '{self.anti_cheating_secret}' > /tmp/anti_cheating_secret5566.txt")
            # show contents of directories for debugging
            ret, out, err = self._ssh_exec_command(f"ls -lAFgR {self.submission_dir}")
            # # do required installs on QEMU VM
            # ret, out, err = self._ssh_exec_command("sudo python3 -m pip install termcolor")
            # ret, out, err = self._ssh_exec_command("sudo DEBIAN_FRONTEND=noninteractive apt-get update", True)
            # ret, out, err = self._ssh_exec_command("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q curl frr", True)
            # ret, out, err = self._ssh_exec_command("sudo DEBIAN_FRONTEND=noninteractive apt-get clean", True)
            # ret, out, err = self._ssh_exec_command("sudo rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*", True)

        self.init_complete = True

        return self.init_complete


    def _wait_for_sshd(self, hostname: str=None, port: int=None, total_wait: int = 120, interval: int = 10) -> bool:
        """Wait until the QEMU VM sshd is initialized, which we test by looking for the SSH banner."""
        print(f"\n==> BGPHVirtualMachine._wait_for_sshd()")

        if hostname is None:
            hostname = self.hostipv4
        if port is None:
            port = self.SSH_FWD_PORT

        # first, wait until the QEMU VM is running and accepting TCP connections
        deadline = time.time() + total_wait
        while time.time() < deadline:
            print(f"Attempting socket.create_connection() ({hostname}:{port} @ {time.asctime(time.localtime())})")
            try:
                s = socket.create_connection((hostname, port), timeout=2)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                s.close()
                break
            except OSError:
                time.sleep(interval)

        # wait for the SSH banner — use SO_LINGER to avoid TIME_WAIT accumulation
        deadline = time.time() + total_wait
        while time.time() < deadline:
            try:
                s = socket.create_connection((hostname, port), timeout=15)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                s.settimeout(15)
                banner = s.recv(256)
                s.close()
                print(f"sshd banner [{banner}] @ {time.asctime(time.localtime())}")
                if banner.startswith(b"SSH-"):
                    return True
            except (OSError, ConnectionResetError, socket.timeout) as e:
                print(f"sshd error  [{e}] @ {time.asctime(time.localtime())}")
            time.sleep(interval)
        return False


    def shutdown(self):
        print(f"\n==> BGPHVirtualMachine.shutdown()")
        ret, out, err = self._ssh_exec_command("sudo shutdown now")


    def send_cmd(self, shell, cmd: str, sleep_sec=2):
        print(f"\n==> BGPHVirtualMachine.send_cmd()")
        shell.send(cmd + '\n')
        print(f"     {cmd}")
        time.sleep(sleep_sec)


    def start_topology(self, shell, total_timeout=120) -> Result:
        print(f"\n==> BGPHVirtualMachine.start_topology()")
        self.send_cmd(shell, f"cd {self.BGPHijacking_dir} && sudo python3 bgp.py", 30)
        output = ""
        shell.settimeout(10)

        print("Waiting for topology to start")
        deadline = time.time() + total_timeout
        while "*** Starting CLI:" not in output:
            if time.time() > deadline:
                return Result(False, f"Topology did not start within {total_timeout}s, please check bgp.py, output: {output}")
            try:
                chunk = shell.recv(2048).decode()
                output += chunk
                print(f"** recv chunk ({len(chunk):>4} bytes), total output: {len(output):>6} bytes: [{chunk}]")
            except socket.timeout:
                print(f"recv timed out, {int(deadline - time.time())}s remaining")

        print(output)
        self.topology_start_output = output
        return Result(True)


    def get_anti_cheating_secret(self) -> str:
        return self.anti_cheating_secret


    def get_topology_start_output(self):
        print(f"\n==> BGPHVirtualMachine.get_topology_start_output()")
        return self.topology_start_output


    def stop_topology(self, shell):
        """
        Must use the same shell as start_topology
        """
        print(f"\n==> BGPHVirtualMachine.stop_topology()")
        self.send_cmd(shell, "exit", 5)


    def start_rogue(self, use_hard=False) -> Result:
        print(f"\n==> BGPHVirtualMachine.start_rogue()")
        script = "start_rogue_hard.sh" if use_hard else "start_rogue.sh"
        ret, out, err = self._ssh_exec_command(f"cd {self.BGPHijacking_dir} && bash ./{script}")
        time.sleep(5)
        return Result(ret == 0, err if ret != 0 else "")



    def stop_rogue(self) -> Result:
        print(f"\n==> BGPHVirtualMachine.stop_rogue()")
        ret, out, err = self._ssh_exec_command(f"cd {self.BGPHijacking_dir} && bash ./stop_rogue.sh")
        time.sleep(5)
        return Result(ret == 0, err if ret != 0 else "")


    # def check_website(self, shell, host="h5-1") -> str:
    def check_website(self, host="h5-1") -> str:
        print(f"\n==> BGPHVirtualMachine.check_website()")
        ret, out, err = self._ssh_exec_command(
            f"sudo python3 {self.BGPHijacking_dir}/run.py --node {host} --cmd 'curl -s 11.0.1.1'")
        return out


    # def bgp_messages(self, shell, router="R3") -> str:
    def bgp_messages(self, router="R3") -> str:
        print(f"\n==> BGPHVirtualMachine.bgp_messages()")
        ret, out, err = self._ssh_exec_command(
            f"sudo python3 {self.BGPHijacking_dir}/run.py --node {router} --cmd \"vtysh -c 'show ip bgp'\"")
        return out

    # def do_extra_checks(self, shell):
    def do_extra_checks(self):
        print(f"\n==> BGPHVirtualMachine.do_extra_checks()")
        return
        ret, out1, err = self._ssh_exec_command("ps -ef | grep webserver")
        ret, out2, err = self._ssh_exec_command("ls -lAF /tmp/anti_cheating_secret5566.txt")
        return out1 + "\n\n" + out2
