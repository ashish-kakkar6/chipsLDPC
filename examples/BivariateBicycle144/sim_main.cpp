#ifdef BP_ONLY_ARTIFACT
#include "VBpOnlyArtifact.h"
#else
#include "VBpFilteredOsd0Artifact.h"
#endif
#include "verilated.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>

#ifdef BP_ONLY_ARTIFACT
using Dut = VBpOnlyArtifact;
#else
using Dut = VBpFilteredOsd0Artifact;
#endif

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
  for (int bit = 0; bit < width; ++bit) setBit(port, offset + bit, value >> bit & 1);
}

template <typename T> static int signedField(const T &port, int offset, int width) {
  int value = 0;
  for (int bit = 0; bit < width; ++bit) value |= int(getBit(port, offset + bit)) << bit;
  return value & (1 << (width - 1)) ? value - (1 << width) : value;
}

static void tick(Dut &dut) {
  dut.clock = 0;
  dut.eval();
  dut.clock = 1;
  dut.eval();
}

[[noreturn]] static void fail(const std::string &message) {
  std::cerr << "FAIL: " << message << '\n';
  std::exit(1);
}

static std::vector<int> readValues(std::istream &input, int count, const char *name) {
  std::vector<int> values(count);
  for (auto &value : values)
    if (!(input >> value)) fail(std::string("malformed ") + name);
  return values;
}

struct Frame {
  int status, iterations, cycles, bpCycles, osdCycles, selected, activeRows, solverCycles;
  std::vector<int> soft, correction;
  std::vector<std::pair<int, int>> stream;
};

static Frame decode(
    Dut &dut, const std::vector<int> &syndrome, const std::vector<int> &prior,
    int magnitudeBits, int accumulatorBits, int maxCycles) {
  const int m = syndrome.size(), n = prior.size();
  dut.inputValid = 0;
  dut.scopeValid = 0;
  dut.correctionReady = 1;
  dut.resultReady = 1;
  clearPort(dut.syndrome);
  clearPort(dut.prior);
  clearPort(dut.scope);
  dut.reset = 1;
  tick(dut);
  dut.reset = 0;
  for (int row = 0; row < m; ++row) setBit(dut.syndrome, row, syndrome[row]);
  for (int col = 0; col < n; ++col)
    setField(dut.prior, col * magnitudeBits, magnitudeBits, prior[col]);
  dut.inputValid = 1;
  dut.eval();
  if (!dut.inputReady) fail("input was not ready");
  tick(dut);
  dut.inputValid = 0;

  Frame frame{};
  frame.correction.assign(n, 0);
  std::vector<int> seen(n, 0);
  int elapsed = 0, lastAt = -1;
  while (!dut.resultValid && elapsed < maxCycles) {
    if (dut.correctionValid) {
      const int index = dut.correctionIndex;
      if (index < 0 || index >= n || seen[index]) fail("invalid correction index stream");
      seen[index] = 1;
      frame.correction[index] = dut.correctionValue;
      frame.stream.emplace_back(index, int(dut.correctionValue));
      if (dut.correctionLast) {
        if (lastAt >= 0) fail("multiple correction.last assertions");
        lastAt = frame.stream.size() - 1;
      }
    }
    tick(dut);
    ++elapsed;
  }
  if (!dut.resultValid) fail("decoder timeout");
  if (!frame.stream.empty() && lastAt != int(frame.stream.size()) - 1)
    fail("correction.last was not on the final item");
  frame.status = dut.status;
  frame.iterations = dut.completedIterations;
  frame.cycles = dut.cycles;
  frame.bpCycles = dut.bpCycles;
  frame.osdCycles = dut.osdCycles;
  frame.selected = dut.selected;
  frame.activeRows = dut.activeRows;
  frame.solverCycles = dut.solverCycles;
  frame.soft.resize(n);
  for (int col = 0; col < n; ++col)
    frame.soft[col] = signedField(dut.softOutput, col * accumulatorBits, accumulatorBits);
  if (frame.cycles != elapsed) fail("reported and observed cycle counts differ");
  tick(dut);
  return frame;
}

static const char *statusName(int status, bool bpOnly) {
  if (bpOnly && status == 2) return "bp_nonconverged";
  static const char *names[] = {"bp_converged", "osd_solved", "osd_inconsistent", "osd_overflow"};
  return status >= 0 && status < 4 ? names[status] : "invalid";
}

struct Timing {
  int dispatch, bp, bpOutput, sort, solverRows, solverMesh, osdOutput, osdControl;
};

struct ArtifactConfig {
  int m, n, magnitudeBits, accumulatorBits, threshold;
  std::vector<int> prefixes;
};

static ArtifactConfig readConfig(std::istream &input) {
  ArtifactConfig config{};
  int count;
  if (!(input >> config.m >> config.n >> config.magnitudeBits >> config.accumulatorBits
              >> config.threshold >> count) || count < 0)
    fail("invalid artifact configuration");
  config.prefixes = readValues(input, count, "artifact prefixes");
  if (!config.prefixes.empty() && (config.prefixes.front() < 1 ||
      config.prefixes.back() > config.n ||
      !std::is_sorted(config.prefixes.begin(), config.prefixes.end()) ||
      std::adjacent_find(config.prefixes.begin(), config.prefixes.end()) != config.prefixes.end()))
    fail("invalid artifact prefixes");
  return config;
}

static Timing breakdown(
  const Frame &frame, int n, int eligible, const std::vector<int> &prefixes) {
  const bool bpOnly = prefixes.empty();
  const bool bp = frame.status == 0;
  const int bpOutput = bp || bpOnly ? frame.stream.size() : 0;
  const int sort = bp || bpOnly ? 0 : n + eligible;
  const int osdOutput = !bpOnly && frame.status == 1 ? frame.stream.size() : 0;
  int solverMesh = 0;
  if (frame.solverCycles)
    for (int prefix : prefixes) {
      solverMesh += 3 * prefix + 1;
      if (frame.selected <= prefix) break;
    }
  const int solverRows = frame.solverCycles - solverMesh;
  const int osdControl = bpOnly ? 0 : frame.osdCycles - sort - frame.solverCycles - osdOutput;
  const int dispatch = frame.cycles - frame.bpCycles - frame.osdCycles - bpOutput;
  if (dispatch < 0 || osdControl < 0 || solverMesh < 0) fail("invalid timing decomposition");
  return {dispatch, frame.bpCycles, bpOutput, sort, solverRows, solverMesh, osdOutput, osdControl};
}

template <typename T> static void writeArray(std::ostream &out, const std::vector<T> &values) {
  out << '[';
  for (std::size_t i = 0; i < values.size(); ++i) {
    if (i) out << ',';
    out << values[i];
  }
  out << ']';
}

static int exactMain(const char *goldenPath, const char *resultPath) {
  std::ifstream input(goldenPath);
  const auto config = readConfig(input);
  const auto syndrome = readValues(input, config.m, "golden syndrome");
  const auto prior = readValues(input, config.n, "golden prior");
  Frame expected{};
  int eligible, correctionCount;
  input >> expected.status >> expected.iterations >> expected.cycles >> expected.bpCycles
        >> expected.osdCycles >> expected.selected >> expected.activeRows
        >> expected.solverCycles >> eligible;
  expected.soft = readValues(input, config.n, "golden soft output");
  input >> correctionCount;
  for (int i = 0, index, value; i < correctionCount; ++i) {
    input >> index >> value;
    expected.stream.emplace_back(index, value);
  }
  std::string extra;
  if (!input || input >> extra) fail("malformed or excess golden data");

  Dut dut;
  const auto actual = decode(
    dut, syndrome, prior, config.magnitudeBits, config.accumulatorBits,
    4 * config.n + 2 * config.m + 3 * std::accumulate(
      config.prefixes.begin(), config.prefixes.end(), 0) +
      2 * expected.iterations + 128);
#define CHECK(field) if (actual.field != expected.field) fail(#field " differs from software golden")
  CHECK(status); CHECK(iterations); CHECK(cycles); CHECK(bpCycles); CHECK(osdCycles);
  CHECK(selected); CHECK(activeRows); CHECK(solverCycles); CHECK(soft); CHECK(stream);
#undef CHECK
  const int observedEligible = std::count_if(actual.soft.begin(), actual.soft.end(),
    [&config](int value) { return std::abs(value) < config.threshold; });
  if (observedEligible != eligible) fail("eligible count differs from software golden");
  const auto timing = breakdown(actual, config.n, eligible, config.prefixes);
  std::vector<int> correctionOnes;
  for (int col = 0; col < config.n; ++col)
    if (actual.correction[col]) correctionOnes.push_back(col);

  std::ofstream output(resultPath);
  output << "{\n  \"status\":\"" << statusName(actual.status, config.prefixes.empty())
         << "\",\n  \"iterations\":" << actual.iterations
         << ",\n  \"eligible\":" << eligible << ",\n  \"selected\":" << actual.selected
         << ",\n  \"active_rows\":" << actual.activeRows << ",\n  \"timing_cycles\":{"
         << "\"total\":" << actual.cycles << ",\"dispatch\":" << timing.dispatch
         << ",\"bp\":" << timing.bp << ",\"bp_output\":" << timing.bpOutput
         << ",\"sort\":" << timing.sort << ",\"solver_rows\":" << timing.solverRows
         << ",\"solver_mesh\":" << timing.solverMesh
         << ",\"osd_output\":" << timing.osdOutput
         << ",\"osd_control\":" << timing.osdControl << "},\n  \"soft_outputs\":";
  writeArray(output, actual.soft);
  output << ",\n  \"correction_ones\":";
  writeArray(output, correctionOnes);
  output << "\n}\n";
  dut.final();
  std::cout << "PASS: exact emitted BB144 RTL matched the independent golden; result: "
            << resultPath << '\n';
  return 0;
}

static int benchmarkMain(
    const char *inputPath, const char *csvPath, const char *configPath) {
  std::ifstream input(inputPath);
  std::ifstream artifactConfig(configPath);
  const auto config = readConfig(artifactConfig);
  int m, n, logicalCount, iterations, codeCycles, pCount, magnitudeBits, controlMax;
  if (!(input >> m >> n >> logicalCount >> iterations >> codeCycles >> pCount
              >> magnitudeBits >> controlMax) || logicalCount <= 0 || logicalCount > 32)
    fail("invalid benchmark header");
  if (m != config.m || n != config.n || magnitudeBits != config.magnitudeBits)
    fail("benchmark and artifact dimensions differ");
  std::vector<std::vector<int>> logicals(logicalCount);
  for (auto &logical : logicals) {
    int degree;
    input >> degree;
    logical = readValues(input, degree, "logical row");
  }
  std::ofstream csv(csvPath);
  if (!csv) fail("cannot create benchmark output");
  csv << "p,shot,status,converged,iterations,total_cycles,dispatch_cycles,bp_cycles,"
         "bp_output_cycles,sort_cycles,solver_row_cycles,solver_mesh_cycles,"
         "osd_output_cycles,osd_control_cycles,eligible,selected,active_rows,"
         "correction_weight,predicted_observables,actual_observables,logical_failure\n";
  Dut dut;
  const bool bpOnly = config.prefixes.empty();
  int totalShots = 0;
  for (int point = 0; point < pCount; ++point) {
    double p;
    int shots;
    input >> p >> shots;
    const auto prior = readValues(input, n, "benchmark prior");
    for (int shot = 0; shot < shots; ++shot) {
      const auto syndrome = readValues(input, m, "benchmark syndrome");
      const auto observedBits = readValues(input, logicalCount, "logical observables");
      const auto frame = decode(
        dut, syndrome, prior, magnitudeBits, config.accumulatorBits,
        4 * n + 2 * m + 3 * std::accumulate(
          config.prefixes.begin(), config.prefixes.end(), 0) +
          2 * iterations + 128);
      const int eligible = std::count_if(frame.soft.begin(), frame.soft.end(),
        [&config](int value) { return std::abs(value) < config.threshold; });
      if (frame.status == 0 && frame.selected != 0) fail("BP result selected OSD columns");
      if (!bpOnly && frame.status != 0 && std::find(
            config.prefixes.begin(), config.prefixes.end(), frame.selected) == config.prefixes.end())
        fail("selected count is not a configured OSD prefix");
      if (bpOnly && frame.status != 0 && frame.status != 2)
        fail("invalid BP-only status");
      if (frame.status == 3) fail("all-column ranking must not overflow");
      const int expectedCount = bpOnly ? n :
        frame.status == 0 ? n : frame.status == 1 ? frame.selected : 0;
      if (int(frame.stream.size()) != expectedCount) fail("unexpected correction stream length");

      uint32_t predicted = 0, observed = 0;
      for (int logical = 0; logical < logicalCount; ++logical) {
        bool parity = false;
        for (int column : logicals[logical]) parity ^= frame.correction[column];
        predicted |= uint32_t{parity} << logical;
        observed |= uint32_t{observedBits[logical] != 0} << logical;
      }
      const bool success = frame.status == 0 || (!bpOnly && frame.status == 1);
      const bool logicalFailure = !success || predicted != observed;
      const auto timing = breakdown(frame, n, eligible, config.prefixes);
      const int weight = std::count(frame.correction.begin(), frame.correction.end(), 1);
      csv << std::setprecision(12) << p << ',' << shot << ','
          << statusName(frame.status, bpOnly)
          << ',' << int(frame.status == 0) << ',' << frame.iterations << ',' << frame.cycles
          << ',' << timing.dispatch << ',' << timing.bp << ',' << timing.bpOutput
          << ',' << timing.sort << ',' << timing.solverRows << ',' << timing.solverMesh
          << ',' << timing.osdOutput << ',' << timing.osdControl << ',' << eligible
          << ',' << frame.selected << ',' << frame.activeRows << ',' << weight << ",0x"
          << std::hex << predicted << ",0x" << observed << std::dec << ','
          << int(logicalFailure) << '\n';

      ++totalShots;
    }
  }
  std::string extra;
  if (input >> extra) fail("extra benchmark data");
  dut.final();
  std::cout << "PASS: simulated " << totalShots << " BB144 shots; raw results: "
            << csvPath << '\n';
  return 0;
}

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  if (argc == 5 && std::string(argv[1]) == "--benchmark")
    return benchmarkMain(argv[2], argv[3], argv[4]);
  if (argc != 3) {
    std::cerr << "usage: <simulator> <golden.txt> <result.json>\n"
                 "   or: <simulator> --benchmark <input> <shots.csv> "
                 "<artifact-config>\n";
    return 2;
  }
  return exactMain(argv[1], argv[2]);
}
