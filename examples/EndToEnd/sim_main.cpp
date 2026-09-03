#include "VStaticTannerArtifact.h"
#include "verilated.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

using Dut = VStaticTannerArtifact;

template <typename T> static void clearPort(T &port) {
  if constexpr (VlIsVlWide<T>::value)
    for (std::size_t word = 0; word < T::Words; ++word) port.at(word) = 0;
  else
    port = 0;
}

template <typename T> static void setBit(T &port, int bit, bool value) {
  if constexpr (VlIsVlWide<T>::value) {
    const auto mask = uint32_t{1} << (bit % 32);
    auto &word = port.at(bit / 32);
    word = value ? word | mask : word & ~mask;
  } else {
    const auto mask = uint64_t{1} << bit;
    const auto word = static_cast<uint64_t>(port);
    port = static_cast<T>(value ? word | mask : word & ~mask);
  }
}

template <typename T> static bool getBit(const T &port, int bit) {
  if constexpr (VlIsVlWide<T>::value)
    return (port.at(bit / 32) >> (bit % 32)) & 1U;
  else
    return (static_cast<uint64_t>(port) >> bit) & 1U;
}

template <typename T> static void setField(T &port, int offset, int width, int value) {
  for (int bit = 0; bit < width; ++bit) setBit(port, offset + bit, (value >> bit) & 1);
}

template <typename T> static int signedField(const T &port, int offset, int width) {
  uint64_t value = 0;
  for (int bit = 0; bit < width; ++bit)
    value |= uint64_t{getBit(port, offset + bit)} << bit;
  return value & (uint64_t{1} << (width - 1))
    ? static_cast<int>(value - (uint64_t{1} << width))
    : static_cast<int>(value);
}

static void tick(Dut &dut) {
  dut.clock = 0;
  dut.eval();
  dut.clock = 1;
  dut.eval();
}

static void expect(int iteration, const std::string &name, int actual, int golden) {
  if (actual != golden) {
    std::cerr << "FAIL iteration " << iteration << ": " << name << " = "
              << actual << ", golden = " << golden << '\n';
    std::exit(1);
  }
}

static std::vector<int> readValues(std::istream &input, int count, const std::string &name) {
  std::vector<int> values(count);
  for (auto &value : values)
    if (!(input >> value)) {
      std::cerr << "malformed golden " << name << '\n';
      std::exit(2);
    }
  return values;
}

template <typename T> static void writeArray(std::ostream &out, const std::vector<T> &values) {
  out << '[';
  for (std::size_t i = 0; i < values.size(); ++i) {
    if (i) out << ',';
    out << values[i];
  }
  out << ']';
}

static int exactMain(int argc, char **argv) {
  const std::string mode = argc == 4 ? argv[3] : "full";
  if ((argc != 3 && argc != 4) || (mode != "full" && mode != "compact")) {
    std::cerr << "usage: VStaticTannerArtifact <golden.txt> <result.json> [full|compact]\n";
    return 2;
  }
  std::ifstream input(argv[1]);
  int m, n, magnitudeBits, accumulatorBits, iterations, priorScale;
  if (!(input >> m >> n >> magnitudeBits >> accumulatorBits >> iterations >> priorScale)
      || m <= 0 || n <= 0 || magnitudeBits <= 0 || accumulatorBits <= 1
      || accumulatorBits >= 63 || iterations <= 0 || priorScale <= 0) {
    std::cerr << "invalid golden header\n";
    return 2;
  }
  const auto syndrome = readValues(input, m, "syndrome");
  const auto priors = readValues(input, n, "prior");

  Dut dut;
  dut.loadValid = 0;
  dut.stepValid = 0;
  dut.stepControl = 0;
  clearPort(dut.syndrome);
  clearPort(dut.prior);
  dut.reset = 1;
  tick(dut);
  dut.reset = 0;

  for (int i = 0; i < m; ++i) setBit(dut.syndrome, i, syndrome[i]);
  for (int i = 0; i < n; ++i) setField(dut.prior, i * magnitudeBits, magnitudeBits, priors[i]);
  dut.loadValid = 1;
  dut.eval();
  expect(0, "loadReady", dut.loadReady, 1);
  tick(dut);
  dut.loadValid = 0;

  std::vector<int> finalMarginal, finalCorrection, finalResidual;
  int finalConverged = 0;
  for (int iteration = 1; iteration <= iterations; ++iteration) {
    int control, expectedConverged;
    if (!(input >> control)) {
      std::cerr << "missing golden iteration " << iteration << '\n';
      return 2;
    }
    const auto expectedMarginal = readValues(input, n, "marginal");
    const auto expectedCorrection = readValues(input, n, "correction");
    const auto expectedResidual = readValues(input, m, "residual");
    if (!(input >> expectedConverged)) {
      std::cerr << "missing golden convergence\n";
      return 2;
    }

    dut.stepControl = control;
    dut.stepValid = 1;
    dut.eval();
    expect(iteration, "stepReady", dut.stepReady, 1);
    tick(dut);
    dut.stepValid = 0;
    expect(iteration, "resultValid after CNU", dut.resultValid, 0);
    tick(dut);
    expect(iteration, "resultValid after VNU", dut.resultValid, 1);

    finalMarginal.resize(n);
    finalCorrection.resize(n);
    finalResidual.resize(m);
    for (int i = 0; i < n; ++i) {
      finalMarginal[i] = signedField(dut.marginal, i * accumulatorBits, accumulatorBits);
      finalCorrection[i] = getBit(dut.correction, i);
      expect(iteration, "marginal[" + std::to_string(i) + "]", finalMarginal[i], expectedMarginal[i]);
      expect(iteration, "correction[" + std::to_string(i) + "]", finalCorrection[i], expectedCorrection[i]);
    }
    for (int i = 0; i < m; ++i) {
      finalResidual[i] = getBit(dut.residual, i);
      expect(iteration, "residual[" + std::to_string(i) + "]", finalResidual[i], expectedResidual[i]);
    }
    finalConverged = dut.converged;
    expect(iteration, "converged", finalConverged, expectedConverged);
  }

  std::string extra;
  if (input >> extra) {
    std::cerr << "extra data after final golden record\n";
    return 2;
  }
  std::ofstream result(argv[2]);
  if (!result) {
    std::cerr << "cannot write " << argv[2] << '\n';
    return 2;
  }
  if (mode == "compact") {
    result << "{\n  \"soft_outputs\":";
    writeArray(result, finalMarginal);
    result << ",\n  \"corrections\":";
    writeArray(result, finalCorrection);
  } else {
    result << "{\n  \"iterations\":" << iterations << ",\n  \"correction\":";
    writeArray(result, finalCorrection);
    result << ",\n  \"marginal\":";
    writeArray(result, finalMarginal);
    result << ",\n  \"approx_error_probability\":[" << std::setprecision(12);
    for (int i = 0; i < n; ++i) {
      if (i) result << ',';
      result << 1.0 / (1.0 + std::exp(static_cast<double>(finalMarginal[i]) / priorScale));
    }
    result << "],\n  \"residual\":";
    writeArray(result, finalResidual);
  }
  result << ",\n  \"converged\":" << (finalConverged ? "true" : "false") << "\n}\n";
  dut.final();
  std::cout << "PASS: exact emitted RTL matched " << iterations
            << " Scala golden iterations; result: " << argv[2] << '\n';
  return 0;
}

static int benchmarkMain(const char *inputPath, const char *outputPath) {
  std::ifstream input(inputPath);
  int m, n, logicalCount, iterations, cycles, pCount, magnitudeBits, controlMax;
  if (!(input >> m >> n >> logicalCount >> iterations >> cycles >> pCount
              >> magnitudeBits >> controlMax)
      || m <= 0 || n <= 0 || logicalCount <= 0 || logicalCount > 32
      || iterations <= 0 || cycles <= 0 || pCount <= 0 || magnitudeBits <= 0
      || controlMax < 0) {
    std::cerr << "invalid benchmark header\n";
    return 2;
  }
  std::vector<std::vector<int>> logicals(logicalCount);
  for (auto &logical : logicals) {
    int degree;
    if (!(input >> degree) || degree < 0) return 2;
    logical = readValues(input, degree, "logical row");
    if (std::any_of(logical.begin(), logical.end(), [n](int column) {
          return column < 0 || column >= n;
        })) return 2;
  }
  std::ofstream output(outputPath);
  if (!output) {
    std::cerr << "cannot write " << outputPath << '\n';
    return 2;
  }
  output << "p,shot,converged,predicted_observables,actual_observables,logical_failure\n";
  Dut dut;
  for (int point = 0; point < pCount; ++point) {
    double p;
    int shots;
    if (!(input >> p >> shots) || !(p > 0.0 && p < 0.5) || shots <= 0) return 2;
    const auto priors = readValues(input, n, "prior");
    for (int shot = 0; shot < shots; ++shot) {
      const auto syndrome = readValues(input, m, "syndrome");
      const auto actual = readValues(input, logicalCount, "logical observables");
      dut.loadValid = 0;
      dut.stepValid = 0;
      dut.stepControl = 0;
      clearPort(dut.syndrome);
      clearPort(dut.prior);
      dut.reset = 1;
      tick(dut);
      dut.reset = 0;
      for (int i = 0; i < m; ++i) setBit(dut.syndrome, i, syndrome[i]);
      for (int i = 0; i < n; ++i)
        setField(dut.prior, i * magnitudeBits, magnitudeBits, priors[i]);
      dut.loadValid = 1;
      dut.eval();
      if (!dut.loadReady) return 3;
      tick(dut);
      dut.loadValid = 0;
      for (int iteration = 1; iteration <= iterations; ++iteration) {
        dut.stepControl = std::min(iteration, controlMax);
        dut.stepValid = 1;
        dut.eval();
        if (!dut.stepReady) return 3;
        tick(dut);
        dut.stepValid = 0;
        tick(dut);
        if (!dut.resultValid) return 3;
      }
      uint32_t predicted = 0, observed = 0;
      for (int logical = 0; logical < logicalCount; ++logical) {
        bool parity = false;
        for (int column : logicals[logical]) parity ^= getBit(dut.correction, column);
        predicted |= uint32_t{parity} << logical;
        observed |= uint32_t{actual[logical] != 0} << logical;
      }
      output << std::setprecision(12) << p << ',' << shot << ','
             << int(dut.converged) << ",0x" << std::hex << predicted << ",0x"
             << observed << std::dec << ',' << int(predicted != observed) << '\n';
    }
  }
  std::string extra;
  if (input >> extra) {
    std::cerr << "extra data after final benchmark record\n";
    return 2;
  }
  dut.final();
  std::cout << "PASS: simulated benchmark shots; raw results: " << outputPath << '\n';
  return 0;
}

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  if (argc == 4 && std::string(argv[1]) == "--benchmark")
    return benchmarkMain(argv[2], argv[3]);
  return exactMain(argc, argv);
}
