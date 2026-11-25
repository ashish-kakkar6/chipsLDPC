"""Compile the harness port helpers against real installed Verilator headers."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class VerilatorPortsTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_scalar_and_wide_ports_across_word_boundaries(self):
        # An override also permits checking an older release's include directory
        # without replacing the system installation. CI uses Ubuntu's package.
        include_override = os.environ.get("CHIPSLDPC_VERILATOR_INCLUDE")
        if include_override:
            include = Path(include_override)
        elif shutil.which("verilator"):
            root = subprocess.run(
                ["verilator", "--getenv", "VERILATOR_ROOT"], check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            include = Path(root) / "include"
        else:
            self.skipTest("Verilator headers unavailable")
        self.assertTrue((include / "verilated.h").is_file(), str(include))

        source = (Path(__file__).resolve().parents[1] / "benchmarks/bb144/sim_main.cpp").read_text()
        # Exercise the production functions without requiring generated RTL or
        # a simulated decoder. Do not duplicate the port implementation here.
        helpers = source[source.index("template <typename T> static void clearPort"):
                         source.index("static void tick")]
        checks = r"""
template <typename T> void checkScalar() {
  constexpr int bits = sizeof(T) * 8;
  T port = std::numeric_limits<T>::max();
  clearPort(port);
  assert(port == 0);
  for (int bit = 0; bit < bits; ++bit) {
    setBit(port, bit, true);
    assert(static_cast<uint64_t>(port) == (uint64_t{1} << bit));
    for (int other = 0; other < bits; ++other)
      assert(getBit(port, other) == (other == bit));
    setBit(port, bit, false);
    assert(port == 0);
  }
  port = std::numeric_limits<T>::max();
  for (int bit = 0; bit < bits; ++bit) {
    setBit(port, bit, false);
    assert(!getBit(port, bit));
    setBit(port, bit, true);
    assert(port == std::numeric_limits<T>::max());
  }
}

template <std::size_t Words> void checkWide() {
  VlWide<Words> port;
  for (std::size_t word = 0; word < Words; ++word) port.at(word) = UINT32_MAX;
  clearPort(port);
  for (std::size_t word = 0; word < Words; ++word) assert(port.at(word) == 0);
  for (int bit = 0; bit < int(Words * 32); ++bit) {
    setBit(port, bit, true);
    for (std::size_t word = 0; word < Words; ++word)
      assert(port.at(word) == (word == std::size_t(bit / 32) ? uint32_t{1} << (bit % 32) : 0));
    for (int other = 0; other < int(Words * 32); ++other)
      assert(getBit(port, other) == (other == bit));
    setBit(port, bit, false);
    for (std::size_t word = 0; word < Words; ++word) assert(port.at(word) == 0);
  }
  // Clearing one bit must preserve the other bits, including adjacent words.
  for (std::size_t word = 0; word < Words; ++word) port.at(word) = UINT32_MAX;
  for (int bit = 0; bit < int(Words * 32); ++bit) {
    setBit(port, bit, false);
    for (std::size_t word = 0; word < Words; ++word)
      assert(port.at(word) == (word == std::size_t(bit / 32) ?
          UINT32_MAX ^ (uint32_t{1} << (bit % 32)) : UINT32_MAX));
    setBit(port, bit, true);
  }
}

template <typename T> void checkFields(T &port, int bits, int offset, int width) {
  const int sign = 1 << (width - 1);
  for (int value : {-sign, -sign + 1, -1, 0, 1, sign - 1}) {
    clearPort(port);
    for (int bit = 0; bit < bits; ++bit) setBit(port, bit, bit % 3 == 0);
    setField(port, offset, width, value);
    assert(signedField(port, offset, width) == value);
    for (int bit = 0; bit < bits; ++bit) {
      const bool expected = bit >= offset && bit < offset + width ?
          (static_cast<uint32_t>(value) >> (bit - offset)) & 1U : bit % 3 == 0;
      assert(getBit(port, bit) == expected);
    }
  }
}

int main() {
  checkScalar<CData>();
  checkScalar<SData>();
  checkScalar<IData>();
  checkScalar<QData>();
  checkWide<3>();
  checkWide<5>();  // The failing CI softOutput port is VlWide<5>.
  checkWide<8>();
  CData c = 0; SData s = 0; IData i = 0; QData q = 0;
  checkFields(c, 8, 0, 8);
  checkFields(s, 16, 5, 8);
  checkFields(i, 32, 24, 8);
  checkFields(q, 64, 28, 8);  // Straddles bit 31/32 within a scalar port.
  checkFields(q, 64, 56, 8);  // Includes bit 63.
  VlWide<5> wide;
  for (int offset : {0, 28, 60, 92, 124, 152}) checkFields(wide, 160, offset, 8);
  for (int offset : {27, 59, 91, 123}) checkFields(wide, 160, offset, 15);
}
"""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            test = directory / "ports.cpp"
            binary = directory / "ports"
            test.write_text(
                '#include "verilated.h"\n#include <cassert>\n#include <cstdint>\n'
                '#include <limits>\n#include <type_traits>\n' + helpers + checks
            )
            subprocess.run(
                ["c++", "-std=c++17", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(include), str(test), "-o", str(binary)], check=True,
            )
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
