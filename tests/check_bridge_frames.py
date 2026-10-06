"""Compile the pinned upstream BLE frame writer against a non-radio test harness.

Run directly with Python 3 and a C++ compiler. Downloads only the immutable public
component source, or accepts --source for an offline source file.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    package = (root / "meshcore_homeassistant/ble_bridge_package.yaml").read_text()
    refs = re.findall(r"^\s+ref: ([0-9a-f]{40})$", package, re.MULTILINE)
    if len(refs) != 1:
        raise RuntimeError("Expected exactly one immutable bridge revision")
    if args.source:
        source = args.source.read_text()
    else:
        url = ("https://raw.githubusercontent.com/matthew73210/meshcore-ble-bridge/"
               + refs[0] + "/components/meshcore_ble_bridge/meshcore_ble_bridge.cpp")
        with urlopen(url, timeout=30) as response:
            source = response.read().decode()
    # Use the actual pinned implementation, not a second implementation of it.
    start = source.index("void MeshCoreBLEBridge::write_ble_(")
    end = source.index("void MeshCoreBLEBridge::pump_ble_tx_queue_()", start)
    method = source[start:end]
    harness = r'''
#include <cassert>
#include <cstdint>
#include <vector>
#include <string>
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
class MeshCoreBLEBridge {
 public:
  bool ble_ready_ = true;
  uint16_t rx_handle_ = 1;
  bool write_with_response_ = true;
  size_t mtu = 185;
  int pumps = 0;
  int errors = 0;
  static constexpr uint8_t ERR_CODE_ILLEGAL_ARG = 6;
  std::vector<std::vector<uint8_t>> ble_tx_queue_;
  size_t ble_payload_limit_() const { return mtu - 3; }
  void send_error_to_tcp_(uint8_t error) { assert(error == 6); ++errors; }
  void pump_ble_tx_queue_() { ++pumps; }
  void write_ble_(const uint8_t *data, size_t len);
};
'''
    harness += method
    harness += r'''
int main() {
  const std::string prompt = "Start OptimusPrime every 30s, prefix ping? 1 confirm, cancel. Expires 2 min.";
  std::vector<uint8_t> frame(13, 0);
  frame[0] = 2;
  frame.insert(frame.end(), prompt.begin(), prompt.end());
  // Reproduce the old bridge's exact seven-character symptom.
  assert(std::string(frame.begin() + 13, frame.begin() + 20) == "Start O");
  MeshCoreBLEBridge bridge;
  bridge.write_ble_(frame.data(), frame.size());
  assert(bridge.ble_tx_queue_.size() == 1);
  assert(bridge.ble_tx_queue_.front() == frame);
  assert(bridge.pumps == 1 && bridge.errors == 0);
  // A maximum-sized direct message must also stay one complete command.
  std::vector<uint8_t> maximum(163, 0x61);
  maximum[0] = 2;
  bridge.write_ble_(maximum.data(), maximum.size());
  assert(bridge.ble_tx_queue_.size() == 2);
  assert(bridge.ble_tx_queue_.back() == maximum);
  // Multi-byte UTF-8 must not be split into separate commands either.
  std::vector<uint8_t> unicode(13, 0);
  for (int i = 0; i < 30; ++i) { unicode.push_back(0xC3); unicode.push_back(0xA9); }
  bridge.write_ble_(unicode.data(), unicode.size());
  assert(bridge.ble_tx_queue_.size() == 3 && bridge.ble_tx_queue_.back() == unicode);
  // With response enabled, upstream delegates long writes to the GATT stack.
  bridge.mtu = 23;
  bridge.write_ble_(frame.data(), frame.size());
  assert(bridge.ble_tx_queue_.size() == 4 && bridge.ble_tx_queue_.back() == frame);
  // Without response, oversize writes must fail instead of silently truncating.
  bridge.write_with_response_ = false;
  bridge.write_ble_(frame.data(), frame.size());
  assert(bridge.errors == 1 && bridge.ble_tx_queue_.size() == 4);
  bridge.ble_ready_ = false;
  bridge.write_ble_(frame.data(), frame.size());
  assert(bridge.ble_tx_queue_.size() == 4);
}
'''
    with tempfile.TemporaryDirectory(prefix="meshcore-bridge-test-") as temporary:
        cpp = Path(temporary) / "frames.cpp"
        binary = Path(temporary) / "frames"
        cpp.write_text(harness)
        subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        str(cpp), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print("Pinned bridge frame tests passed; no radio traffic sent.")


if __name__ == "__main__":
    main()
