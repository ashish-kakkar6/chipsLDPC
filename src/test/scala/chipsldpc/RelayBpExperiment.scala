package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import chisel3.util.{Cat, Enum, log2Ceil}
import java.nio.file.{Files, Path, Paths}
import org.scalatest.freespec.AnyFreeSpec

private[chipsldpc] final case class RelayBpExperimentProfile(
    initialIterations: Int = 80,
    relayIterations: Int = 60,
    relayLegs: Int = 600,
    solutionTarget: Int = 5,
    seedOffset: Int = 0,
) {
  require(initialIterations > 0 && relayIterations > 0)
  require(relayLegs >= 0)
  require(solutionTarget > 0)
  require(seedOffset >= 0 && seedOffset < (1 << LfsrRelayCoefficients.StateBits) - 1)
  require(
    BigInt(initialIterations) + BigInt(relayLegs) * relayIterations <=
      RelayBpConfig.MaximumIterations,
  )

  def decoderConfig(problem: DecoderProblem): RelayBpConfig = RelayBpConfig(
    problem.nodes, initialIterations, relayIterations, relayLegs + 1,
    solutionTarget, seedOffset,
  )
}

/** BB benchmark ABI around Relay-BP, with a replaceable downstream processor. */
private final class RelayBpArtifact(problem: DecoderProblem, config: RelayBpConfig) extends Module {
  override def desiredName: String = "RelayBpArtifact"
  private val graph = problem.graph
  private val q = config.q
  private val indexBits = math.max(1, log2Ceil(problem.n))
  private val streamConfig = SparseBitmaskStreamerConfig(problem.n)

  val inputValid = IO(Input(Bool()))
  val inputReady = IO(Output(Bool()))
  val legLimit = IO(Input(UInt(config.legBits.W)))
  val syndrome = IO(Input(UInt(graph.checkCount.W)))
  val prior = IO(Input(UInt((problem.n * q.magnitudeBits).W)))
  val scopeValid = IO(Input(Bool()))
  val scope = IO(Input(UInt(problem.n.W)))
  val correctionValid = IO(Output(Bool()))
  val correctionReady = IO(Input(Bool()))
  val correctionIndex = IO(Output(UInt(indexBits.W)))
  val correctionValue = IO(Output(Bool()))
  val correctionLast = IO(Output(Bool()))
  val resultValid = IO(Output(Bool()))
  val resultReady = IO(Input(Bool()))
  val status = IO(Output(UInt(2.W)))
  val completedIterations = IO(Output(UInt(config.iterationBits.W)))
  val cycles = IO(Output(UInt(32.W)))
  val bpCycles = IO(Output(UInt((config.iterationBits + 1).W)))
  val osdCycles = IO(Output(UInt(32.W)))
  val selected = IO(Output(UInt(1.W)))
  val activeRows = IO(Output(UInt(1.W)))
  val solverCycles = IO(Output(UInt(32.W)))
  val softOutput = IO(Output(UInt((problem.n * q.accumulatorBits).W)))
  val legsExecuted = IO(Output(UInt(config.legBits.W)))
  val solutionsFound = IO(Output(UInt(config.solutionBits.W)))
  val legTraceValid = IO(Output(Bool()))
  val legTraceIndex = IO(Output(UInt(config.legBits.W)))
  val legTraceIterations = IO(Output(UInt(config.localIterationBits.W)))
  val legTraceConverged = IO(Output(Bool()))

  private val sIdle :: sBp :: sOutput :: Nil = Enum(3)
  private val state = RegInit(sIdle)
  private val cycleCount = RegInit(0.U(32.W))
  private val bp = Module(new RelayBpDecoder(config, runtimeLegLimit = true))
  private val outcome = Reg(chiselTypeOf(bp.io.out.bits))
  private val streamer = Module(new SparseBitmaskStreamer(streamConfig))

  bp.io.in.valid := state === sIdle && inputValid
  bp.legLimit.get := legLimit
  bp.io.in.bits.syndrome.zipWithIndex.foreach { case (bit, i) => bit := syndrome(i) }
  bp.io.in.bits.prior.zipWithIndex.foreach { case (value, i) =>
    value := prior((i + 1) * q.magnitudeBits - 1, i * q.magnitudeBits)
  }
  bp.io.out.ready := state === sBp && streamer.io.in.ready
  streamer.io.in.valid := state === sBp && bp.io.out.valid
  streamer.io.in.bits := bp.io.out.bits.correction.asUInt
  streamer.io.out.ready := state === sOutput && correctionReady
  streamer.io.done.ready := state === sOutput && resultReady

  inputReady := state === sIdle && bp.io.in.ready
  correctionValid := state === sOutput && streamer.io.out.valid
  correctionIndex := streamer.io.out.bits.index
  correctionValue := true.B
  correctionLast := streamer.io.out.bits.last
  resultValid := state === sOutput && streamer.io.done.valid
  status := Mux(outcome.success, 0.U, 2.U)
  completedIterations := outcome.totalIterations
  cycles := cycleCount
  bpCycles := outcome.totalIterations << 1
  osdCycles := 0.U
  selected := 0.U
  activeRows := 0.U
  solverCycles := 0.U
  softOutput := Cat(outcome.marginal.reverse.map(_.asUInt))
  legsExecuted := outcome.legsExecuted
  solutionsFound := outcome.solutionsFound
  legTraceValid := bp.io.legTrace.valid
  legTraceIndex := bp.io.legTrace.bits.index
  legTraceIterations := bp.io.legTrace.bits.iterations
  legTraceConverged := bp.io.legTrace.bits.converged

  when(inputValid && inputReady) {
    cycleCount := 0.U
    state := sBp
  }.elsewhen(state =/= sIdle && !resultValid) {
    cycleCount := cycleCount + 1.U
  }

  when(state === sBp && bp.io.out.fire) {
    outcome := bp.io.out.bits
    state := sOutput
  }.elsewhen(state === sOutput && streamer.io.done.fire) {
    state := sIdle
  }
}

object RelayBpExperiment {
  private val sparseStreamAbi = 2
  private val legTraceAbi = 1
  val defaultProfile = RelayBpExperimentProfile()
  private def bit(value: Boolean): Int = if (value) 1 else 0

  private[chipsldpc] def parseProfile(values: Seq[String]): RelayBpExperimentProfile = {
    if (values.isEmpty) defaultProfile
    else {
      require(values.size == 5, "expected T0 Tr R S seedOffset")
      val parsed = values.map(_.toInt)
      RelayBpExperimentProfile(parsed(0), parsed(1), parsed(2), parsed(3), parsed(4))
    }
  }

  private[chipsldpc] def artifactConfig(
      problem: DecoderProblem,
      config: RelayBpConfig,
  ): Seq[Int] = Seq(
    problem.graph.checkCount, problem.n, config.q.magnitudeBits,
    config.q.accumulatorBits, 0, 0,
    sparseStreamAbi, SparseBitmaskStreamerConfig(problem.n).bankWidth,
    config.initialIterations, config.relayIterations, config.maximumLegs,
    config.solutionTarget, config.seedOffset, legTraceAbi,
  )

  private[chipsldpc] def golden(problem: DecoderProblem, config: RelayBpConfig): String = {
    val beta = Reference.lfsrBeta(problem.n, config.maximumLegs, config.seedOffset)
    val outcome = Reference.runRelay(config, problem.prior, problem.syndrome, beta)
    val streamConfig = SparseBitmaskStreamerConfig(problem.n)
    val correctionIndices = outcome.correction.zipWithIndex.collect { case (true, index) => index }
    val occupiedBanks = correctionIndices.map(_ / streamConfig.bankWidth).distinct.size
    val correction = correctionIndices.flatMap(index => Seq(index, 1))
    val legTrace = outcome.legOutcomes.zipWithIndex.flatMap { case (leg, index) =>
      Seq(index, leg.iterations, 2 * leg.iterations, bit(leg.converged))
    }
    Seq(
      artifactConfig(problem, config), problem.syndrome.map(bit), problem.prior,
      Seq(
        if (outcome.success) 0 else 2,
        outcome.iterations,
        2 * outcome.iterations + 1 + occupiedBanks + correctionIndices.size,
        2 * outcome.iterations,
        0, 0, 0, 0, 0,
        outcome.legs,
        outcome.solutions,
      ),
      Seq(outcome.legOutcomes.size) ++ legTrace,
      outcome.state.marginal,
      Seq(correctionIndices.size) ++ correction,
    ).map(_.mkString(" ")).mkString("", "\n", "\n")
  }

  private[chipsldpc] def writeGolden(
      problem: DecoderProblem,
      config: RelayBpConfig,
      output: Path,
  ): Unit = {
    Files.createDirectories(output.getParent)
    Files.writeString(output, golden(problem, config))
  }

  private def writeConfig(problem: DecoderProblem, config: RelayBpConfig, output: Path): Unit = {
    val streamConfig = SparseBitmaskStreamerConfig(problem.n)
    val figure7 = config.initialIterations == 80 && config.relayIterations == 60 &&
      config.maximumLegs == 601 && config.solutionTarget == 5
    Files.writeString(output.resolve("artifact/config.txt"),
      artifactConfig(problem, config).mkString(" ") + "\n")
    Files.writeString(output.resolve("artifact/config.json"), ujson.Obj(
      "schema" -> "chipsldpc.bb144-relay-bp.v2",
      "decoder" -> "relay_bp_s",
      "profile" -> (if (figure7) "fpga-paper-figure-7-parameters-relay-5-int4.2.8" else "custom"),
      "paper" -> "arXiv:2510.21600v1 Figure 7",
      "initial_iterations" -> config.initialIterations,
      "relay_iterations" -> config.relayIterations,
      "paper_R_relay_legs_after_initial" -> (config.maximumLegs - 1),
      "paper_R_interpretation" -> "Algorithm_1_and_trmue_num_sets",
      "maximum_legs_total" -> config.maximumLegs,
      "maximum_total_iterations" -> config.maximumIterations,
      "solution_target" -> config.solutionTarget,
      "seed_offset" -> config.seedOffset,
      "coefficient_source" -> "per-variable_16-bit_galois_lfsr_x16+x14+x13+x11+1",
      "coefficient_frame_policy" -> "reseed_each_frame",
      "initial_beta" -> LfsrRelayCoefficients.InitialBeta,
      "initial_gamma" -> 0.125,
      "relay_beta_min" -> 3,
      "relay_beta_max" -> 10,
      "requested_relay_gamma_min" -> -0.24,
      "requested_relay_gamma_max" -> 0.66,
      "effective_quantized_relay_gamma_min" -> -0.25,
      "effective_quantized_relay_gamma_max" -> 0.625,
      "integer_format" -> "int4.2.8",
      "prior_scale" -> RelayDefaults.priorScale,
      "beta_scale" -> RelayDefaults.memoryScale,
      "beta_fractional_bits" -> config.format.fractionalBits,
      "candidate_selection" -> "minimum_prior_score_first_tie_wins",
      "soft_output" -> "final_leg_marginal",
      "correction_output" -> "best_converged_solution_else_final_leg_estimate",
      "status" -> "0_if_any_relay_solution_else_2",
      "correction_stream_abi" -> sparseStreamAbi,
      "correction_stream" -> "ascending_sparse_ones",
      "correction_bank_width" -> streamConfig.bankWidth,
      "empty_correction" -> "zero stream entries; resultValid completes the frame",
      "leg_trace_abi" -> legTraceAbi,
      "leg_trace" -> "one nonblocking terminal-VNU event per executed leg",
      "leg_trace_cycles" -> "measured between consecutive event clock boundaries",
      "cycle_formula" -> "2*completed_iterations+1+occupied_banks+correction_weight",
      "leg_control_cycles" -> 0,
      "paper_decoder_clock_period_ns" -> 12,
      "paper_bp_iteration_ns" -> 24,
      "message_bits" -> config.q.magnitudeBits,
      "soft_bits" -> config.q.accumulatorBits,
      "m" -> problem.graph.checkCount,
      "n" -> problem.n,
    ).render(indent = 2) + "\n")
  }

  def main(args: Array[String]): Unit = {
    require(args.length == 2 || args.length == 7,
      "usage: RelayBpExperiment <problem.json> <output-directory> [T0 Tr R S seedOffset]")
    val problem = DecoderProblem.read(Paths.get(args(0)))
    val profile = parseProfile(args.drop(2).toSeq)
    val config = profile.decoderConfig(problem)
    val output = Paths.get(args(1))
    Files.createDirectories(output.resolve("verification"))
    Files.createDirectories(output.resolve("artifact"))
    writeGolden(problem, config, output.resolve("verification/golden.txt"))
    writeConfig(problem, config, output)
    Generate.emitSystemVerilogFiles(
      () => new RelayBpArtifact(problem, config), output.resolve("artifact/rtl"),
    )
    println(output.toAbsolutePath)
  }
}

object RelayBpSweepGolden {
  def main(args: Array[String]): Unit = {
    require(args.length >= 7 && (args.length - 5) % 2 == 0,
      "usage: RelayBpSweepGolden T0 Tr R S seedOffset (<problem.json> <golden.txt>)+")
    val profile = RelayBpExperiment.parseProfile(args.take(5).toSeq)
    args.drop(5).grouped(2).foreach { pair =>
      val problem = DecoderProblem.read(Paths.get(pair(0)))
      RelayBpExperiment.writeGolden(
        problem, profile.decoderConfig(problem), Paths.get(pair(1)),
      )
    }
  }
}

final class RelayBpArtifactSpec extends AnyFreeSpec with ChiselSim {
  private val problem = DecoderProblem.parse(
    """{"schema":1,"n":3,"row_ones":[[0,1,2]],"prior":[1,1,1],"syndrome":[1],"iterations":1}""",
  )
  private val profile = RelayBpExperimentProfile(
    initialIterations = 1, relayIterations = 1, relayLegs = 2,
    solutionTarget = 1, seedOffset = 17,
  )
  private val config = profile.decoderConfig(problem)

  "the default experiment profile is Figure 7 Relay-5" in {
    assert(RelayBpExperiment.defaultProfile == RelayBpExperimentProfile(
      initialIterations = 80, relayIterations = 60, relayLegs = 600,
      solutionTarget = 5, seedOffset = 0,
    ))
    assert(RelayBpExperiment.defaultProfile.decoderConfig(problem).maximumLegs == 601)
  }

  private def pack(values: Seq[Int], width: Int): BigInt =
    values.zipWithIndex.foldLeft(BigInt(0)) { case (word, (value, index)) =>
      word | BigInt(value) << (index * width)
    }

  private def signedField(value: BigInt, index: Int): Int = {
    val width = config.q.accumulatorBits
    val field = (value >> (index * width)) & ((BigInt(1) << width) - 1)
    if (field.testBit(width - 1)) (field - (BigInt(1) << width)).toInt else field.toInt
  }

  "matches the independent Relay model and sparse-stream timing" in {
    val beta = Reference.lfsrBeta(problem.n, config.maximumLegs, config.seedOffset)
    val expected = Reference.runRelay(config, problem.prior, problem.syndrome, beta)
    val indices = expected.correction.zipWithIndex.collect { case (true, index) => index }
    val occupiedBanks = indices.map(_ / SparseBitmaskStreamerConfig(problem.n).bankWidth).distinct.size
    val expectedCycles = 2 * expected.iterations + 1 + occupiedBanks + indices.size

    simulate(new RelayBpArtifact(problem, config)) { dut =>
      dut.inputValid.poke(false.B)
      dut.legLimit.poke(config.maximumLegs.U)
      dut.scopeValid.poke(false.B)
      dut.scope.poke(0.U)
      dut.correctionReady.poke(true.B)
      dut.resultReady.poke(true.B)
      dut.reset.poke(true.B)
      dut.clock.step()
      dut.reset.poke(false.B)

      for (_ <- 0 until 2) {
        dut.syndrome.poke(pack(problem.syndrome.map(if (_) 1 else 0), 1).U)
        dut.prior.poke(pack(problem.prior, config.q.magnitudeBits).U)
        dut.inputValid.poke(true.B)
        dut.inputReady.expect(true.B)
        dut.clock.step()
        dut.inputValid.poke(false.B)

        val observed = Vector.newBuilder[Int]
        val observedLegs = Vector.newBuilder[(Int, Int, Int, Boolean)]
        var elapsed = 0
        var previousBoundary = 0
        while (!dut.resultValid.peek().litToBoolean && elapsed <= expectedCycles) {
          if (dut.legTraceValid.peek().litToBoolean) {
            val boundary = elapsed + 1
            observedLegs += ((
              dut.legTraceIndex.peek().litValue.toInt,
              dut.legTraceIterations.peek().litValue.toInt,
              boundary - previousBoundary,
              dut.legTraceConverged.peek().litToBoolean,
            ))
            previousBoundary = boundary
          }
          if (dut.correctionValid.peek().litToBoolean) {
            dut.correctionValue.expect(true.B)
            observed += dut.correctionIndex.peek().litValue.toInt
          }
          dut.clock.step()
          elapsed += 1
        }
        assert(elapsed == expectedCycles)
        assert(observed.result() == indices)
        assert(observedLegs.result() == expected.legOutcomes.zipWithIndex.map {
          case (leg, index) => (index, leg.iterations, 2 * leg.iterations, leg.converged)
        })
        dut.status.expect((if (expected.success) 0 else 2).U)
        dut.completedIterations.expect(expected.iterations.U)
        dut.bpCycles.expect((2 * expected.iterations).U)
        dut.cycles.expect(expectedCycles.U)
        dut.legsExecuted.expect(expected.legs.U)
        dut.solutionsFound.expect(expected.solutions.U)
        val soft = dut.softOutput.peek().litValue
        expected.state.marginal.indices.foreach { index =>
          assert(signedField(soft, index) == expected.state.marginal(index))
        }
        dut.clock.step()
        dut.inputReady.expect(true.B)
      }
    }
  }
}
