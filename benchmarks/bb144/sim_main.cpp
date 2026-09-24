#ifdef RELAY_BP_ARTIFACT
#include "VRelayBpArtifact.h"
#elif defined(BP_ONLY_ARTIFACT)
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

#ifdef RELAY_BP_ARTIFACT
using Dut = VRelayBpArtifact;
#elif defined(BP_ONLY_ARTIFACT)
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

static void reset(Dut &dut) {
  dut.inputValid = 0;
  dut.scopeValid = 0;
  dut.correctionReady = 1;
  dut.resultReady = 1;
#ifdef BP_ONLY_ARTIFACT
  dut.iterationLimit = 1;
#endif
#ifdef RELAY_BP_ARTIFACT
  dut.legLimit = 1;
#endif
  clearPort(dut.syndrome);
  clearPort(dut.prior);
  clearPort(dut.scope);
  dut.reset = 1;
  tick(dut);
  dut.reset = 0;
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

struct LegTiming {
  int index, iterations, cycles, converged;
};

static bool operator==(const LegTiming &a, const LegTiming &b) {
  return a.index == b.index && a.iterations == b.iterations &&
    a.cycles == b.cycles && a.converged == b.converged;
}

struct Frame {
  int status, iterations, cycles, bpCycles, osdCycles, selected, activeRows, solverCycles;
  int legsExecuted = 0, solutionsFound = 0;
  std::vector<int> soft, correction;
  std::vector<std::pair<int, int>> stream;
  std::vector<LegTiming> legTimings;
};

static void checkSparseOnes(const Frame &frame) {
  int previous = -1;
  for (const auto &[index, value] : frame.stream) {
    if (value != 1) fail("sparse correction contained a zero value");
    if (index <= previous) fail("sparse correction indices were not strictly ascending");
    previous = index;
  }
}

static Frame decode(
    Dut &dut, const std::vector<int> &syndrome, const std::vector<int> &prior,
    int magnitudeBits, int accumulatorBits, int runtimeLimit, int64_t maxCycles) {
  const int m = syndrome.size(), n = prior.size();
  dut.inputValid = 0;
  dut.scopeValid = 0;
  dut.correctionReady = 1;
  dut.resultReady = 1;
  clearPort(dut.syndrome);
  clearPort(dut.prior);
  clearPort(dut.scope);
#ifdef BP_ONLY_ARTIFACT
  dut.iterationLimit = runtimeLimit;
#endif
#ifdef RELAY_BP_ARTIFACT
  dut.legLimit = runtimeLimit;
#endif
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
  int64_t elapsed = 0;
  int lastAt = -1;
  int previousLegBoundary = 0;
  while (!dut.resultValid && elapsed < maxCycles) {
#ifdef RELAY_BP_ARTIFACT
    if (dut.legTraceValid) {
      const int boundary = static_cast<int>(elapsed) + 1;
      frame.legTimings.push_back({
        int(dut.legTraceIndex), int(dut.legTraceIterations),
        boundary - previousLegBoundary, int(dut.legTraceConverged),
      });
      previousLegBoundary = boundary;
    }
#endif
    if (dut.correctionValid && dut.correctionReady) {
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
#ifdef RELAY_BP_ARTIFACT
  frame.legsExecuted = dut.legsExecuted;
  frame.solutionsFound = dut.solutionsFound;
#endif
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
  int sparseBankWidth = 0;
  int initialIterations = 0, relayIterations = 0, maximumLegs = 0;
  int solutionTarget = 0, seedOffset = 0, maximumIterations = 0;
  std::vector<int> prefixes;
};

static ArtifactConfig readConfig(std::istream &input) {
  ArtifactConfig config{};
  int count;
  if (!(input >> config.m >> config.n >> config.magnitudeBits >> config.accumulatorBits
              >> config.threshold >> count) || count < 0)
    fail("invalid artifact configuration");
  config.prefixes = readValues(input, count, "artifact prefixes");
#if defined(BP_ONLY_ARTIFACT) || defined(RELAY_BP_ARTIFACT)
  int streamAbi;
  if (!(input >> streamAbi >> config.sparseBankWidth) ||
      streamAbi != 2 || config.sparseBankWidth <= 0)
    fail("invalid sparse correction stream configuration");
#endif
#ifdef BP_ONLY_ARTIFACT
  if (!(input >> config.maximumIterations) || config.maximumIterations <= 0)
    fail("invalid BP iteration capacity");
#endif
#ifdef RELAY_BP_ARTIFACT
  int legTraceAbi;
  if (!(input >> config.initialIterations >> config.relayIterations >>
      config.maximumLegs >> config.solutionTarget >> config.seedOffset >> legTraceAbi) ||
      config.initialIterations <= 0 || config.relayIterations <= 0 ||
      config.maximumLegs <= 0 || config.solutionTarget <= 0 || config.seedOffset < 0 ||
      config.seedOffset >= 65535 || legTraceAbi != 1)
    fail("invalid Relay-BP configuration");
  const auto maximum = static_cast<int64_t>(config.initialIterations) +
    static_cast<int64_t>(config.maximumLegs - 1) * config.relayIterations;
  if (maximum > 1000000000) fail("Relay-BP iteration limit is too large");
  config.maximumIterations = maximum;
#endif
  if (!config.prefixes.empty() && (config.prefixes.front() < 1 ||
      config.prefixes.back() > config.n ||
      !std::is_sorted(config.prefixes.begin(), config.prefixes.end()) ||
      std::adjacent_find(config.prefixes.begin(), config.prefixes.end()) != config.prefixes.end()))
    fail("invalid artifact prefixes");
  return config;
}

static int decoderRuntimeLimit(const ArtifactConfig &config, int budget) {
#ifdef BP_ONLY_ARTIFACT
  if (budget < 1 || budget > config.maximumIterations) fail("BP budget exceeds artifact capacity");
  return budget;
#elif defined(RELAY_BP_ARTIFACT)
  if (budget < config.initialIterations ||
      (budget - config.initialIterations) % config.relayIterations)
    fail("Relay budget must equal T0 + R*Tr");
  const int legs = 1 + (budget - config.initialIterations) / config.relayIterations;
  if (legs > config.maximumLegs) fail("Relay budget exceeds artifact capacity");
  return legs;
#else
  (void)config; (void)budget;
  return 0;
#endif
}

#ifdef RELAY_BP_ARTIFACT
static void checkRelayTiming(const Frame &frame, const ArtifactConfig &config) {
  if (int(frame.legTimings.size()) != frame.legsExecuted ||
      frame.legsExecuted < 1 || frame.legsExecuted > config.maximumLegs ||
      frame.solutionsFound < 0 || frame.solutionsFound > config.solutionTarget)
    fail("invalid Relay leg or solution count");
  int iterations = 0, cycles = 0, solutions = 0;
  for (std::size_t index = 0; index < frame.legTimings.size(); ++index) {
    const auto &leg = frame.legTimings[index];
    const int limit = index == 0 ? config.initialIterations : config.relayIterations;
    if (leg.index != int(index) || leg.iterations < 1 || leg.iterations > limit ||
        leg.cycles != 2 * leg.iterations)
      fail("invalid Relay leg trace record");
    iterations += leg.iterations;
    cycles += leg.cycles;
    solutions += leg.converged;
  }
  if (iterations != frame.iterations || cycles != frame.bpCycles ||
      solutions != frame.solutionsFound)
    fail("Relay leg trace totals differ from decoder totals");
}
#endif

static void checkSparseTiming(const Frame &frame, int bankWidth) {
  checkSparseOnes(frame);
  int occupiedBanks = 0, previousBank = -1;
  for (const auto &entry : frame.stream) {
    const int bank = entry.first / bankWidth;
    if (bank != previousBank) ++occupiedBanks;
    previousBank = bank;
  }
  const int expected = 2 * frame.iterations + 1 + occupiedBanks +
    int(frame.stream.size());
  if (frame.bpCycles != 2 * frame.iterations || frame.cycles != expected)
    fail("sparse correction timing contract violated");
}

static Timing breakdown(
  const Frame &frame, int n, int eligible, const std::vector<int> &prefixes,
  int sparseBankWidth) {
  const bool bpOnly = sparseBankWidth > 0;
  const bool bp = frame.status == 0;
  const int bpOutput = bpOnly ? frame.cycles - frame.bpCycles - 1 :
    bp ? frame.stream.size() : 0;
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

#ifdef RELAY_BP_ARTIFACT
static void writeLegTraceJson(std::ostream &out, const std::vector<LegTiming> &trace) {
  out << '[';
  for (std::size_t i = 0; i < trace.size(); ++i) {
    if (i) out << ',';
    const auto &leg = trace[i];
    out << "{\"index\":" << leg.index << ",\"iterations\":" << leg.iterations
        << ",\"cycles\":" << leg.cycles << ",\"converged\":"
        << (leg.converged ? "true" : "false") << '}';
  }
  out << ']';
}

static void writeLegTraceCsv(std::ostream &out, const std::vector<LegTiming> &trace) {
  for (std::size_t i = 0; i < trace.size(); ++i) {
    if (i) out << '|';
    const auto &leg = trace[i];
    out << leg.index << ':' << leg.iterations << ':' << leg.cycles << ':' << leg.converged;
  }
}
#endif

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
#ifdef RELAY_BP_ARTIFACT
  input >> expected.legsExecuted >> expected.solutionsFound;
  int legCount;
  input >> legCount;
  if (legCount < 1) fail("invalid golden Relay leg trace length");
  for (int i = 0; i < legCount; ++i) {
    LegTiming leg{};
    input >> leg.index >> leg.iterations >> leg.cycles >> leg.converged;
    expected.legTimings.push_back(leg);
  }
#endif
  expected.soft = readValues(input, config.n, "golden soft output");
  input >> correctionCount;
  for (int i = 0, index, value; i < correctionCount; ++i) {
    input >> index >> value;
    expected.stream.emplace_back(index, value);
  }
  std::string extra;
  if (!input || input >> extra) fail("malformed or excess golden data");

  Dut dut;
  reset(dut);
  const auto actual = decode(
    dut, syndrome, prior, config.magnitudeBits, config.accumulatorBits,
    decoderRuntimeLimit(config, config.maximumIterations),
    4 * config.n + 2 * config.m + 3 * std::accumulate(
      config.prefixes.begin(), config.prefixes.end(), 0) +
      2 * expected.iterations + 128);
  if (config.sparseBankWidth > 0) checkSparseTiming(actual, config.sparseBankWidth);
#ifdef RELAY_BP_ARTIFACT
  checkRelayTiming(actual, config);
#endif
#define CHECK(field) if (actual.field != expected.field) fail(#field " differs from software golden")
  CHECK(status); CHECK(iterations); CHECK(cycles); CHECK(bpCycles); CHECK(osdCycles);
  CHECK(selected); CHECK(activeRows); CHECK(solverCycles); CHECK(soft); CHECK(stream);
#ifdef RELAY_BP_ARTIFACT
  CHECK(legsExecuted); CHECK(solutionsFound); CHECK(legTimings);
#endif
#undef CHECK
  const int observedEligible = std::count_if(actual.soft.begin(), actual.soft.end(),
    [&config](int value) { return std::abs(value) < config.threshold; });
  if (observedEligible != eligible) fail("eligible count differs from software golden");
  const auto timing = breakdown(
    actual, config.n, eligible, config.prefixes, config.sparseBankWidth);
  std::vector<int> correctionOnes;
  for (int col = 0; col < config.n; ++col)
    if (actual.correction[col]) correctionOnes.push_back(col);

  std::ofstream output(resultPath);
  output << "{\n  \"status\":\"" << statusName(actual.status, config.sparseBankWidth > 0)
         << "\",\n  \"iterations\":" << actual.iterations
         << ",\n  \"eligible\":" << eligible << ",\n  \"selected\":" << actual.selected
         << ",\n  \"active_rows\":" << actual.activeRows;
#ifdef RELAY_BP_ARTIFACT
  output << ",\n  \"legs_executed\":" << actual.legsExecuted
         << ",\n  \"solutions_found\":" << actual.solutionsFound
         << ",\n  \"leg_timing\":";
  writeLegTraceJson(output, actual.legTimings);
#endif
  output << ",\n  \"timing_cycles\":{"
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
    const char *inputPath, const char *csvPath, const char *configPath,
    int requestedBudget = 0) {
  std::ifstream input(inputPath);
  std::ifstream artifactConfig(configPath);
  const auto config = readConfig(artifactConfig);
  int m, n, logicalCount, iterations, codeCycles, pCount, magnitudeBits, controlMax;
  if (!(input >> m >> n >> logicalCount >> iterations >> codeCycles >> pCount
              >> magnitudeBits >> controlMax) || logicalCount <= 0 || logicalCount > 32)
    fail("invalid benchmark header");
  if (m != config.m || n != config.n || magnitudeBits != config.magnitudeBits)
    fail("benchmark and artifact dimensions differ");
  const int budget = requestedBudget ? requestedBudget :
    (config.maximumIterations ? config.maximumIterations : iterations);
  const int runtimeLimit = decoderRuntimeLimit(config, budget);
  std::vector<std::vector<int>> logicals(logicalCount);
  for (auto &logical : logicals) {
    int degree;
    input >> degree;
    logical = readValues(input, degree, "logical row");
  }
  std::ofstream csv(csvPath);
  if (!csv) fail("cannot create benchmark output");
  csv << "p,shot,max_bp_iterations,status,converged,iterations,";
#ifdef RELAY_BP_ARTIFACT
  csv << "legs_executed,solutions_found,leg_trace,";
#endif
  csv << "total_cycles,dispatch_cycles,bp_cycles,"
         "bp_output_cycles,sort_cycles,solver_row_cycles,solver_mesh_cycles,"
         "osd_output_cycles,osd_control_cycles,eligible,selected,active_rows,"
         "correction_weight,predicted_observables,actual_observables,logical_failure\n";
  Dut dut;
  reset(dut);
  const bool bpOnly = config.sparseBankWidth > 0;
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
        runtimeLimit,
        4 * n + 2 * m + 3 * std::accumulate(
          config.prefixes.begin(), config.prefixes.end(), 0) +
          2LL * budget + 128);
      const int eligible = std::count_if(frame.soft.begin(), frame.soft.end(),
        [&config](int value) { return std::abs(value) < config.threshold; });
      if (frame.status == 0 && frame.selected != 0) fail("BP result selected OSD columns");
      if (!bpOnly && frame.status != 0 && std::find(
            config.prefixes.begin(), config.prefixes.end(), frame.selected) == config.prefixes.end())
        fail("selected count is not a configured OSD prefix");
      if (bpOnly && frame.status != 0 && frame.status != 2)
        fail("invalid BP-only status");
      if (frame.status == 3) fail("all-column ranking must not overflow");
      if (bpOnly) {
        checkSparseTiming(frame, config.sparseBankWidth);
      } else {
        const int expectedCount = frame.status == 0 ? n :
          frame.status == 1 ? frame.selected : 0;
        if (int(frame.stream.size()) != expectedCount)
          fail("unexpected correction stream length");
      }
#ifdef RELAY_BP_ARTIFACT
      checkRelayTiming(frame, config);
#endif

      uint32_t predicted = 0, observed = 0;
      for (int logical = 0; logical < logicalCount; ++logical) {
        bool parity = false;
        for (int column : logicals[logical]) parity ^= frame.correction[column];
        predicted |= uint32_t{parity} << logical;
        observed |= uint32_t{observedBits[logical] != 0} << logical;
      }
      const bool success = frame.status == 0 || (!bpOnly && frame.status == 1);
      const bool logicalFailure = !success || predicted != observed;
      const auto timing = breakdown(
        frame, n, eligible, config.prefixes, config.sparseBankWidth);
      const int weight = std::count(frame.correction.begin(), frame.correction.end(), 1);
      csv << std::setprecision(12) << p << ',' << shot << ',' << budget << ','
          << statusName(frame.status, bpOnly)
          << ',' << int(frame.status == 0) << ',' << frame.iterations << ',';
#ifdef RELAY_BP_ARTIFACT
      csv << frame.legsExecuted << ',' << frame.solutionsFound << ',';
      writeLegTraceCsv(csv, frame.legTimings);
      csv << ',';
#endif
      csv << frame.cycles
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
  if (argc == 7 && std::string(argv[1]) == "--budget" &&
      std::string(argv[3]) == "--benchmark")
    return benchmarkMain(argv[4], argv[5], argv[6], std::stoi(argv[2]));
  if (argc != 3) {
    std::cerr << "usage: <simulator> <golden.txt> <result.json>\n"
                 "   or: <simulator> --benchmark <input> <shots.csv> "
                 "<artifact-config>\n"
                 "   or: <simulator> --budget <iterations> --benchmark <input> "
                 "<shots.csv> <artifact-config>\n";
    return 2;
  }
  return exactMain(argv[1], argv[2]);
}
