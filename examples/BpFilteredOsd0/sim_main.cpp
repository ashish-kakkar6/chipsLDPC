#include "VBpFilteredOsd0.h"
#include "verilated.h"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <vector>

using Dut = VBpFilteredOsd0;

static void tick(Dut &dut) {
  dut.clock = 0;
  dut.eval();
  dut.clock = 1;
  dut.eval();
}

static void expect(int test, const char *name, int actual, int golden) {
  if (actual != golden) {
    std::cerr << "FAIL case " << test << ": " << name << " = " << actual
              << ", golden = " << golden << '\n';
    std::exit(1);
  }
}

struct Record {
  int syndrome, scopeValid, scope;
  std::array<int, 7> prior;
  int status, iterations, cycles, bpCycles, osdCycles, selected, activeRows, solverCycles;
  std::vector<int> indices, golden;
};

static Record readRecord(std::istream &in) {
  Record r{};
  int count;
  in >> r.syndrome >> r.scopeValid >> r.scope;
  for (auto &prior : r.prior) in >> prior;
  in >> r.status >> r.iterations >> r.cycles >> r.bpCycles >> r.osdCycles
     >> r.selected >> r.activeRows >> r.solverCycles >> count;
  r.indices.resize(count);
  for (auto &index : r.indices) in >> index;
  in >> count;
  r.golden.resize(count);
  for (auto &word : r.golden) in >> word;
  if (!in) {
    std::cerr << "malformed golden record\n";
    std::exit(2);
  }
  return r;
}

static void drive(Dut &dut, const Record &r) {
  dut.io_in_bits_syndrome_0 = r.syndrome & 1;
  dut.io_in_bits_syndrome_1 = r.syndrome >> 1 & 1;
  dut.io_in_bits_syndrome_2 = r.syndrome >> 2 & 1;
  dut.io_in_bits_prior_0 = r.prior[0];
  dut.io_in_bits_prior_1 = r.prior[1];
  dut.io_in_bits_prior_2 = r.prior[2];
  dut.io_in_bits_prior_3 = r.prior[3];
  dut.io_in_bits_prior_4 = r.prior[4];
  dut.io_in_bits_prior_5 = r.prior[5];
  dut.io_in_bits_prior_6 = r.prior[6];
  dut.io_in_bits_inScopeValid = r.scopeValid;
  dut.io_in_bits_inScope_0 = r.scope & 1;
  dut.io_in_bits_inScope_1 = r.scope >> 1 & 1;
  dut.io_in_bits_inScope_2 = r.scope >> 2 & 1;
  dut.io_in_bits_inScope_3 = r.scope >> 3 & 1;
  dut.io_in_bits_inScope_4 = r.scope >> 4 & 1;
  dut.io_in_bits_inScope_5 = r.scope >> 5 & 1;
  dut.io_in_bits_inScope_6 = r.scope >> 6 & 1;
}

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: VBpFilteredOsd0 <golden.txt>\n";
    return 2;
  }
  Verilated::commandArgs(argc, argv);
  std::ifstream input(argv[1]);
  int cases;
  if (!(input >> cases) || cases <= 0) return 2;

  Dut dut;
  dut.io_in_valid = 0;
  dut.io_correction_ready = 1;
  dut.io_result_ready = 1;
  dut.reset = 1;
  tick(dut);
  dut.reset = 0;

  for (int test = 0; test < cases; ++test) {
    const auto r = readRecord(input);
    drive(dut, r);
    dut.io_in_valid = 1;
    dut.eval();
    expect(test, "in.ready", dut.io_in_ready, 1);
    tick(dut);
    dut.io_in_valid = 0;

    int elapsed = 0, position = 0, correction = 0;
    while (!dut.io_result_valid && elapsed < 256) {
      if (dut.io_correction_valid) {
        if (position >= static_cast<int>(r.indices.size())) {
          std::cerr << "FAIL case " << test << ": excess correction\n";
          return 1;
        }
        const int index = dut.io_correction_bits_index;
        expect(test, "correction.index", index, r.indices[position]);
        expect(test, "correction.last", dut.io_correction_bits_last,
               position + 1 == static_cast<int>(r.indices.size()));
        if (dut.io_correction_bits_value) correction |= 1 << index;
        ++position;
      }
      tick(dut);
      ++elapsed;
    }
    expect(test, "result.valid", dut.io_result_valid, 1);
    expect(test, "correction count", position, r.indices.size());
    expect(test, "status", dut.io_result_bits_status, r.status);
    expect(test, "iterations", dut.io_result_bits_iterations, r.iterations);
    expect(test, "cycles", dut.io_result_bits_cycles, r.cycles);
    expect(test, "observed cycles", elapsed, r.cycles);
    expect(test, "BP cycles", dut.io_result_bits_bpCycles, r.bpCycles);
    expect(test, "OSD cycles", dut.io_result_bits_osdCycles, r.osdCycles);
    expect(test, "selected", dut.io_result_bits_selected, r.selected);
    expect(test, "active rows", dut.io_result_bits_activeRows, r.activeRows);
    expect(test, "solver cycles", dut.io_result_bits_solverCycles, r.solverCycles);
    if (!r.golden.empty() && std::find(r.golden.begin(), r.golden.end(), correction) == r.golden.end()) {
      std::cerr << "FAIL case " << test << ": correction differs from the canonical golden\n";
      return 1;
    }
    tick(dut);
  }
  std::string extra;
  if (input >> extra) return 2;
  dut.final();
  std::cout << "PASS: exact emitted BP-filtered-OSD0 RTL matched " << cases
            << " independent BP/GF(2) golden cases\n";
}
