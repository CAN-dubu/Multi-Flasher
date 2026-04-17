import serial
import sys
import time

def check_serial_output(port, baudrate=115200, timeout=10):
    try:
        print(f"Opening {port} at {baudrate} baud...")
        ser = serial.Serial(port, baudrate, timeout=0.05)
        
        # 버퍼 클리어
        ser.reset_input_buffer()
        
        # DTR 토글로 리셋 (선택사항)
        ser.setDTR(False)
        time.sleep(0.1)
        ser.setDTR(True)
        
        print(f"Waiting for data...")
        start_time = time.time()
        total_bytes = 0
        line_count = 0
        
        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                # 가능한 모든 데이터 읽기
                data = ser.read(ser.in_waiting)
                total_bytes += len(data)
                
                try:
                    decoded = data.decode('utf-8', errors='ignore')
                    lines = decoded.split('\n')
                    
                    for line in lines:
                        line = line.strip()
                        if line:
                            print(f"[RX] {line}")
                            line_count += 1
                            
                            # "output :" 문자열 확인
                            if "output" in line.lower():
                                print(f"[SUCCESS] Valid output detected! ({line_count} lines, {total_bytes} bytes)")
                                ser.close()
                                return 0
                except:
                    pass
            
            time.sleep(0.01)
        
        # 타임아웃이지만 데이터를 받았으면 성공
        if total_bytes > 0:
            print(f"[SUCCESS] Received {total_bytes} bytes, {line_count} lines")
            ser.close()
            return 0
        
        ser.close()
        print(f"[FAIL] No data in {timeout} seconds")
        return 1
            
    except serial.SerialException as e:
        print(f"[ERROR] Serial port error: {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_serial.py <PORT> [BAUDRATE]")
        sys.exit(1)
    
    port = sys.argv[1]
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
    sys.exit(check_serial_output(port, baudrate))
