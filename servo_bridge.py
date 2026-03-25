import sys
import re
import rclpy
import serial
from rclpy.node import Node
from std_msgs.msg import Int16, String

class ServoBridge(Node):
    def __init__(self):
        # Node 초기화: ROS2 그래프에서 보이는 노드 이름
        super().__init__('servo_bridge')

        # ------------------------------------------------------------
        # 1) 실행 환경 파라미터 설정
        # ------------------------------------------------------------
        # - port: 아두이노가 연결된 시리얼 포트
        # - baud: 시리얼 통신 속도
        self.declare_parameter('port', '/dev/ttyACM0')
        self.declare_parameter('baud', 115200)
        port = self.get_parameter('port').get_parameter_value().string_value
        baud = self.get_parameter('baud').get_parameter_value().integer_value

        try:
            self.ser = serial.Serial(port, baud, timeout=0.1)
            self.get_logger().info(f'Connected to Arduino: {port} @ {baud}')
        except Exception as error:
            # 시리얼 연결이 안 되면 노드 목적 자체를 수행할 수 없으므로 종료
            self.get_logger().error(f'Failed to connect to Arduino: {error}')
            sys.exit(1)

        # ------------------------------------------------------------
        # 2) 고수준(자연어) 명령 -> 저수준(프로토콜) 명령 매핑
        # ------------------------------------------------------------
        # 팀원이 ROS2에서 "구부려" 같은 명령을 보내면,
        # 아두이노로는 "POSE:BEND" 같이 명확한 문자열을 전달한다.
        self.command_map = {
            '구부려': 'POSE:BEND',
            '펴': 'POSE:OPEN',
            '중립': 'POSE:NEUTRAL',
        }

        # ------------------------------------------------------------
        # 3) ROS2 구독(Subscriber) 등록
        # ------------------------------------------------------------
        # hand_command: String 기반 명령 토픽 (신규 권장 방식)
        self.command_subscription = self.create_subscription(
            String,
            'hand_command',
            self.command_callback,
            10)
        # servo_angle: Int16 각도 토픽 (기존 하위 호환)
        self.angle_subscription = self.create_subscription(
            Int16,
            'servo_angle',
            self.angle_callback,
            10)

    def write_serial(self, command: str) -> None:
        # 아두이노에서 한 줄 단위로 읽기 때문에 줄바꿈을 붙인다
        if not hasattr(self, 'ser') or not self.ser.is_open:
            raise Exception('Serial port is not open')

        line = f'{command}\n'
        self.ser.write(line.encode())
        self.get_logger().debug(f'Sent: {command}')

    def command_callback(self, msg: String) -> None:
        #`hand_command` 토픽(String)을 받아 아두이노 명령으로 변환/전송.
        # 예: "구부려" -> "POSE:BEND"
        raw_command = msg.data.strip()
        serial_command = self.command_map.get(raw_command)

        if serial_command is None:
            # 한글 IME 입력 시 보이지 않는 문자가 끼는 경우가 있어 한글만 추출해 재시도
            normalized = ''.join(re.findall(r'[가-힣]+', raw_command))
            serial_command = self.command_map.get(normalized)

        if serial_command is None:
            self.get_logger().warning(f'Unknown command: {raw_command!r}')
            return

        try:
            self.write_serial(serial_command)
        except Exception as error:
            self.get_logger().error(f'Serial write failed: {error}')
            # 재연결 시도
            self._try_reconnect()

    def angle_callback(self, msg: Int16) -> None:
        #`servo_angle` 토픽(Int16)을 받아 모든 서보 공통 각도로 전송.
        angle = max(0, min(180, int(msg.data)))
        try:
            self.write_serial(f'ANGLE:{angle}')
        except Exception as error:
            self.get_logger().error(f'Serial write failed: {error}')
            # 재연결 시도
            self._try_reconnect()

    def destroy_node(self):
        #노드 종료 시 자원 정리.
        if hasattr(self, 'ser') and self.ser.is_open:
            self.ser.close()
        super().destroy_node()

    def _try_reconnect(self) -> None:
        #시리얼 연결 재시도 (에러 발생 후).
        try:
            if hasattr(self, 'ser') and self.ser.is_open:
                self.ser.close()
            port = self.get_parameter('port').get_parameter_value().string_value
            baud = self.get_parameter('baud').get_parameter_value().integer_value
            self.ser = serial.Serial(port, baud, timeout=0.1)
            self.get_logger().info(f'Reconnected to Arduino: {port} @ {baud}')
        except Exception as error:
            self.get_logger().error(f'Reconnect failed: {error}')

def main(args=None):
    # ROS2 클라이언트 라이브러리 초기화
    rclpy.init(args=args)
    node = ServoBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # 종료 순서: 노드 자원 정리 -> rclpy 종료
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass

if __name__ == '__main__':
    main()
