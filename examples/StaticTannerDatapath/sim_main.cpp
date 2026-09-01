#include "VStaticTannerDatapath.h"
#include "verilated.h"

#include <array>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>

using Dut = VStaticTannerDatapath;

static void tick(Dut &dut) {
  dut.clock = 0;
  dut.eval();
  dut.clock = 1;
  dut.eval();
}

static void expect(std::size_t record, const std::string &name, int actual, int golden) {
  if (actual != golden) {
    std::cerr << "FAIL record " << record << ": " << name << " = " << actual
              << ", golden = " << golden << '\n';
    std::exit(1);
  }
}

static int signed5(int value) { return value & 16 ? value - 32 : value; }

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: VStaticTannerDatapath <golden.txt>\n";
    return 2;
  }
  Verilated::commandArgs(argc, argv);
  std::ifstream input(argv[1]);
  if (!input) {
    std::cerr << "cannot open " << argv[1] << '\n';
    return 2;
  }

  Dut dut;
  dut.io_load_valid = 0;
  dut.io_step_valid = 0;
  dut.reset = 1;
  tick(dut);
  dut.reset = 0;

  std::size_t record = 0;
  int syndrome;
  while (input >> syndrome) {
    std::array<int, 7> priors{}, marginal{};
    int iteration, decisions, residual, converged;
    for (auto &value : priors) input >> value;
    input >> iteration;
    for (auto &value : marginal) input >> value;
    input >> decisions >> residual >> converged;
    if (!input) {
      std::cerr << "malformed golden record " << record << '\n';
      return 2;
    }

    if (iteration == 1) {
      dut.io_load_bits_syndrome_0 = syndrome & 1;
      dut.io_load_bits_syndrome_1 = syndrome >> 1 & 1;
      dut.io_load_bits_syndrome_2 = syndrome >> 2 & 1;
      dut.io_load_bits_prior_0 = priors[0];
      dut.io_load_bits_prior_1 = priors[1];
      dut.io_load_bits_prior_2 = priors[2];
      dut.io_load_bits_prior_3 = priors[3];
      dut.io_load_bits_prior_4 = priors[4];
      dut.io_load_bits_prior_5 = priors[5];
      dut.io_load_bits_prior_6 = priors[6];
      dut.io_load_valid = 1;
      dut.eval();
      expect(record, "load.ready", dut.io_load_ready, 1);
      tick(dut);
      dut.io_load_valid = 0;
    }

    dut.io_step_bits = iteration;
    dut.io_step_valid = 1;
    dut.eval();
    expect(record, "step.ready", dut.io_step_ready, 1);
    tick(dut);
    dut.io_step_valid = 0;
    expect(record, "result.valid after CNU", dut.io_result_valid, 0);
    tick(dut);
    expect(record, "result.valid after VNU", dut.io_result_valid, 1);

    const std::array<int, 7> actualMarginal = {
      signed5(dut.io_result_bits_marginal_0), signed5(dut.io_result_bits_marginal_1),
      signed5(dut.io_result_bits_marginal_2), signed5(dut.io_result_bits_marginal_3),
      signed5(dut.io_result_bits_marginal_4), signed5(dut.io_result_bits_marginal_5),
      signed5(dut.io_result_bits_marginal_6),
    };
    for (int i = 0; i < 7; ++i)
      expect(record, "marginal[" + std::to_string(i) + "]", actualMarginal[i], marginal[i]);
    const int actualDecisions = dut.io_result_bits_decision_0
      | dut.io_result_bits_decision_1 << 1 | dut.io_result_bits_decision_2 << 2
      | dut.io_result_bits_decision_3 << 3 | dut.io_result_bits_decision_4 << 4
      | dut.io_result_bits_decision_5 << 5 | dut.io_result_bits_decision_6 << 6;
    const int actualResidual = dut.io_result_bits_residual_0
      | dut.io_result_bits_residual_1 << 1 | dut.io_result_bits_residual_2 << 2;
    expect(record, "decisions", actualDecisions, decisions);
    expect(record, "residual", actualResidual, residual);
    expect(record, "converged", dut.io_result_bits_converged, converged);
    ++record;
  }
  dut.final();
  std::cout << "PASS: exact emitted RTL matched " << record << " Scala golden records\n";
}
