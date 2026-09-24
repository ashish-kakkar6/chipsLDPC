package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import chisel3.util.{Decoupled, Valid, log2Ceil}
import chipsldpc.graph.{TannerGraph, TannerNodeGraphs}
import org.scalatest.freespec.AnyFreeSpec

private final class TraceRelayCoefficients(trace: Vector[Vector[Int]])
    extends RelayCoefficientSource(trace.head.size, LfsrRelayCoefficients.BetaBits) {
  require(trace.nonEmpty && trace.forall(_.size == variableCount))
  private val indexBits = math.max(1, log2Ceil(trace.size))
  private val index = RegInit(0.U(indexBits.W))
  private val table = VecInit(trace.map(row => VecInit(row.map(_.U(betaBits.W)))))

  when(io.frameStart) {
    index := 0.U
  }.elsewhen(io.advanceLeg && index =/= (trace.size - 1).U) {
    index := index + 1.U
  }
  if (trace.size == 1) io.beta := table.head else io.beta := table(index)
}

private final class RelayCoreHarness(
    nodes: TannerNodeGraphs,
    q: Quantization,
    scale: CheckScale,
    format: RelayFormat,
) extends Module {
  private val graph = nodes.graph
  val io = IO(new Bundle {
    val load = Flipped(Decoupled(new StaticDecoderInput(graph.checkCount, graph.variableCount, q)))
    val step = Flipped(Decoupled(UInt(scale.controlBits.W)))
    val beta = Input(Vec(graph.variableCount, UInt(format.betaBits.W)))
    val restartMessages = Input(Bool())
    val bias = Output(Vec(graph.variableCount, SInt(q.accumulatorBits.W)))
    val commit = Valid(new StaticDecoderResult(graph.checkCount, graph.variableCount, q))
    val result = Valid(new StaticDecoderResult(graph.checkCount, graph.variableCount, q))
  })
  private val core = Module(new StaticTannerCore(nodes, q, scale))
  core.io.load <> io.load
  core.io.step <> io.step
  core.io.restartMessages := io.restartMessages
  core.io.bias.zipWithIndex.foreach { case (bias, i) =>
    bias := RelayBias(core.io.prior(i), core.io.result.bits.marginal(i), io.beta(i), q, format)
  }
  io.bias := core.io.bias
  io.commit := core.io.commit
  io.result := core.io.result
}

final class BpDecodersSpec extends AnyFreeSpec with ChiselSim {
  private type Expected = Reference.DecoderOutcome

  private def nodes(variables: Int, rows: Seq[Seq[Int]]): TannerNodeGraphs =
    TannerNodeGraphs.from(TannerGraph.fromRows(variables, rows))

  private def reset(dut: VanillaBpDecoder): Unit = {
    dut.io.in.valid.poke(false.B)
    dut.io.out.ready.poke(false.B)
    dut.reset.poke(true.B)
    dut.clock.step()
    dut.reset.poke(false.B)
  }

  private def reset(dut: RelayBpDecoder): Unit = {
    dut.io.in.valid.poke(false.B)
    dut.io.out.ready.poke(false.B)
    dut.reset.poke(true.B)
    dut.clock.step()
    dut.reset.poke(false.B)
  }

  private def expectResult(port: BpDecoderResult, expected: Expected): Unit = {
    port.success.expect(expected.success.B)
    port.correction.zip(expected.correction).foreach { case (actual, value) => actual.expect(value.B) }
    port.marginal.zip(expected.state.marginal).foreach { case (actual, value) => actual.expect(value.S) }
    port.residual.zip(expected.residual).foreach { case (actual, value) => actual.expect(value.B) }
    port.totalIterations.expect(expected.iterations.U)
    port.legsExecuted.expect(expected.legs.U)
    port.solutionsFound.expect(expected.solutions.U)
  }

  private def input(
      port: StaticDecoderInput,
      priors: Vector[Int],
      syndrome: Vector[Boolean],
  ): Unit = {
    port.prior.zip(priors).foreach { case (actual, value) => actual.poke(value.U) }
    port.syndrome.zip(syndrome).foreach { case (actual, value) => actual.poke(value.B) }
  }

  private def expectStatic(
      result: StaticDecoderResult,
      state: Reference.DecoderState,
      residual: Vector[Boolean],
  ): Unit = {
    result.marginal.zip(state.marginal).foreach { case (actual, value) => actual.expect(value.S) }
    result.decision.zip(state.decision).foreach { case (actual, value) => actual.expect(value.B) }
    result.residual.zip(residual).foreach { case (actual, value) => actual.expect(value.B) }
    result.converged.expect((!residual.contains(true)).B)
  }

  private def runVanilla(
      dut: VanillaBpDecoder,
      priors: Vector[Int],
      syndrome: Vector[Boolean],
      expected: Expected,
      outputStalls: Int = 0,
  ): Unit = {
    input(dut.io.in.bits, priors, syndrome)
    dut.io.in.valid.poke(true.B)
    dut.io.in.ready.expect(true.B)
    dut.clock.step()
    dut.io.in.valid.poke(false.B)
    var elapsed = 0
    while (!dut.io.out.valid.peek().litToBoolean && elapsed <= 2 * expected.iterations) {
      dut.clock.step()
      elapsed += 1
    }
    assert(elapsed == 2 * expected.iterations)
    expectResult(dut.io.out.bits, expected)
    for (_ <- 0 until outputStalls) {
      dut.clock.step()
      dut.io.out.valid.expect(true.B)
      expectResult(dut.io.out.bits, expected)
    }
    dut.io.out.ready.poke(true.B)
    dut.clock.step()
    dut.io.out.ready.poke(false.B)
    dut.io.in.ready.expect(true.B)
  }

  private def runRelay(
      dut: RelayBpDecoder,
      priors: Vector[Int],
      syndrome: Vector[Boolean],
      expected: Expected,
      outputStalls: Int = 0,
  ): Unit = {
    input(dut.io.in.bits, priors, syndrome)
    dut.io.in.valid.poke(true.B)
    dut.io.in.ready.expect(true.B)
    dut.clock.step()
    dut.io.in.valid.poke(false.B)
    val trace = Vector.newBuilder[(Int, Int, Int, Boolean)]
    var elapsed = 0
    var previousBoundary = 0
    while (!dut.io.out.valid.peek().litToBoolean && elapsed <= 2 * expected.iterations) {
      if (dut.io.legTrace.valid.peek().litToBoolean) {
        val boundary = elapsed + 1
        trace += ((
          dut.io.legTrace.bits.index.peek().litValue.toInt,
          dut.io.legTrace.bits.iterations.peek().litValue.toInt,
          boundary - previousBoundary,
          dut.io.legTrace.bits.converged.peek().litToBoolean,
        ))
        previousBoundary = boundary
      }
      dut.clock.step()
      elapsed += 1
    }
    assert(elapsed == 2 * expected.iterations,
      s"Relay took $elapsed cycles for ${expected.iterations} iterations")
    assert(trace.result() == expected.legOutcomes.zipWithIndex.map { case (outcome, index) =>
      (index, outcome.iterations, 2 * outcome.iterations, outcome.converged)
    })
    expectResult(dut.io.out.bits, expected)
    for (_ <- 0 until outputStalls) {
      dut.clock.step()
      dut.io.out.valid.expect(true.B)
      expectResult(dut.io.out.bits, expected)
    }
    dut.io.out.ready.poke(true.B)
    dut.clock.step()
    dut.io.out.ready.poke(false.B)
    dut.io.in.ready.expect(true.B)
  }

  "vanilla BP remains cycle- and bit-exact across consecutive frames" in {
    val steane = nodes(7, Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)))
    val config = VanillaBpConfig(steane, iterations = 4)
    val priors = Vector(1, 2, 3, 4, 5, 6, 7)
    simulate(new VanillaBpDecoder(config)) { dut =>
      reset(dut)
      for (word <- 0 until 8) {
        val syndrome = Vector.tabulate(3)(bit => ((word >> bit) & 1) != 0)
        runVanilla(
          dut, priors, syndrome, Reference.runVanilla(config, priors, syndrome),
          outputStalls = word % 3,
        )
      }
    }
  }

  "a runtime BP limit reuses a larger elaborated decoder" in {
    val graph = nodes(3, Seq(Seq(0, 1), Seq(1, 2), Seq(0, 2)))
    val capacity = VanillaBpConfig(graph, iterations = 4)
    val limited = capacity.copy(iterations = 1)
    val priors = Vector(2, 1, 1)
    val syndrome = Vector.fill(3)(true)
    val expected = Reference.runVanilla(limited, priors, syndrome)
    simulate(new VanillaBpDecoder(capacity, runtimeIterationLimit = true)) { dut =>
      reset(dut)
      dut.iterationLimit.get.poke(1.U)
      runVanilla(dut, priors, syndrome, expected)
    }
  }

  "a runtime Relay limit stops at a prefix of the elaborated legs" in {
    val graph = nodes(3, Seq(Seq(0, 1), Seq(1, 2), Seq(0, 2)))
    val capacity = RelayBpConfig(
      graph, initialIterations = 1, relayIterations = 1,
      maximumLegs = 3, solutionTarget = 1,
    )
    val limited = capacity.copy(maximumLegs = 1)
    val beta = Vector(Vector.fill(3)(7), Vector.fill(3)(3), Vector.fill(3)(8))
    val priors = Vector(2, 1, 1)
    val syndrome = Vector.fill(3)(true)
    val expected = Reference.runRelay(limited, priors, syndrome, beta.take(1))
    assert(expected.legs == 1)
    simulate(new RelayBpDecoder(
      capacity, Some(() => new TraceRelayCoefficients(beta)), runtimeLegLimit = true,
    )) { dut =>
      reset(dut)
      dut.legLimit.get.poke(1.U)
      runRelay(dut, priors, syndrome, expected)
    }
  }

  "beta eight makes a one-leg Relay decoder identical to vanilla BP" in {
    val steane = nodes(7, Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)))
    val priors = Vector(1, 2, 3, 4, 5, 6, 7)
    val vanillaConfig = VanillaBpConfig(
      steane, iterations = 4, q = RelayDefaults.paperQ,
      scale = RampScale(RelayDefaults.paperQ.magnitudeBits),
    )
    val relayConfig = RelayBpConfig(steane, initialIterations = 4, maximumLegs = 1)
    val beta = Vector(Vector.fill(7)(8))
    for (word <- 0 until 8) {
      val syndrome = Vector.tabulate(3)(bit => ((word >> bit) & 1) != 0)
      val a = Reference.runVanilla(vanillaConfig, priors, syndrome)
      val b = Reference.runRelay(relayConfig, priors, syndrome, beta)
      assert(a == b)
    }
    simulate(new RelayBpDecoder(
      relayConfig, Some(() => new TraceRelayCoefficients(beta)),
    )) { dut =>
      reset(dut)
      for (word <- 0 until 8) {
        val syndrome = Vector.tabulate(3)(bit => ((word >> bit) & 1) != 0)
        runRelay(dut, priors, syndrome, Reference.runRelay(relayConfig, priors, syndrome, beta))
      }
    }
  }

  "later legs replace a heavier solution and incur no control cycles" in {
    val graph = nodes(3, Seq(Seq(0, 1, 2)))
    val config = RelayBpConfig(
      graph, initialIterations = 1, relayIterations = 1,
      maximumLegs = 3, solutionTarget = 2,
    )
    val beta = Vector(Vector.fill(3)(7), Vector.fill(3)(3), Vector(3, 8, 8))
    val priors = Vector.fill(3)(1)
    val syndrome = Vector(true)
    val expected = Reference.runRelay(config, priors, syndrome, beta)
    assert(expected.success && expected.iterations == 3 && expected.legs == 3)
    assert(expected.solutions == 2 && expected.correction == Vector(true, false, false))
    simulate(new RelayBpDecoder(
      config, Some(() => new TraceRelayCoefficients(beta)),
    )) { dut =>
      reset(dut)
      runRelay(dut, priors, syndrome, expected, outputStalls = 4)
    }
  }

  "the shared core preserves marginals, resets messages, and restarts alpha at a leg boundary" in {
    val graph = nodes(3, Seq(Seq(0, 1, 2)))
    val q = RelayDefaults.paperQ
    val scale = RampScale(q.magnitudeBits)
    val format = RelayDefaults.paperFormat
    val priors = Vector.fill(3)(1)
    val syndrome = Vector(true)
    val beta = Vector(Vector.fill(3)(7), Vector.fill(3)(3), Vector(3, 8, 8))
    var expected = Reference.initialize(graph, priors, q)
    val initialMessages = expected.v2c

    simulate(new RelayCoreHarness(graph, q, scale, format)) { dut =>
      dut.io.load.valid.poke(false.B)
      dut.io.step.valid.poke(false.B)
      dut.io.step.bits.poke(1.U)
      dut.io.restartMessages.poke(false.B)
      dut.io.beta.foreach(_.poke(7.U))
      dut.reset.poke(true.B)
      dut.clock.step()
      dut.reset.poke(false.B)

      input(dut.io.load.bits, priors, syndrome)
      dut.io.load.valid.poke(true.B)
      dut.clock.step()
      dut.io.load.valid.poke(false.B)

      beta.zipWithIndex.foreach { case (legBeta, leg) =>
        dut.io.beta.zip(legBeta).foreach { case (actual, value) => actual.poke(value.U) }
        val expectedBias = priors.indices.map { i =>
          Reference.relayBias(priors(i), expected.marginal(i), legBeta(i), format, q)
        }
        dut.io.bias.zip(expectedBias).foreach { case (actual, value) => actual.expect(value.S) }

        dut.io.step.valid.poke(true.B)
        dut.io.step.ready.expect(true.B)
        dut.clock.step()
        dut.io.step.valid.poke(false.B)
        expected = Reference.iterate(graph, expected, syndrome, expectedBias, 1, q, scale)
        val residual = Reference.residual(graph, expected, syndrome)
        dut.io.commit.valid.expect(true.B)
        expectStatic(dut.io.commit.bits, expected, residual)

        dut.io.restartMessages.poke((leg + 1 < beta.size).B)
        dut.clock.step()
        dut.io.restartMessages.poke(false.B)
        dut.io.result.valid.expect(true.B)
        expectStatic(dut.io.result.bits, expected, residual)
        if (leg + 1 < beta.size) expected = expected.copy(v2c = initialMessages)
      }
    }
  }

  "equal-score ties keep the first solution and duplicate solutions count" in {
    val graph = nodes(2, Seq(Seq(0, 1)))
    val config = RelayBpConfig(
      graph, initialIterations = 1, relayIterations = 1,
      maximumLegs = 3, solutionTarget = 2,
    )
    val priors = Vector.fill(2)(1)
    val syndrome = Vector(true)
    val cases = Seq(
      Vector(Vector(7, 7), Vector(3, 8), Vector(8, 3)),
      Vector(Vector(7, 7), Vector(3, 8), Vector(3, 8)),
    )
    cases.foreach { beta =>
      val expected = Reference.runRelay(config, priors, syndrome, beta)
      assert(expected.solutions == 2 && expected.correction == Vector(true, false))
      simulate(new RelayBpDecoder(
        config, Some(() => new TraceRelayCoefficients(beta)),
      )) { dut =>
        reset(dut)
        runRelay(dut, priors, syndrome, expected)
        runRelay(dut, priors, syndrome, expected)
      }
    }
  }

  "failure returns one coherent final-leg snapshot" in {
    val graph = nodes(3, Seq(Seq(0, 1), Seq(1, 2), Seq(0, 2)))
    val config = RelayBpConfig(
      graph, initialIterations = 1, relayIterations = 1,
      maximumLegs = 2, solutionTarget = 1,
    )
    val beta = Vector(Vector.fill(3)(7), Vector.fill(3)(3))
    val priors = Vector(2, 1, 1)
    val syndrome = Vector.fill(3)(true)
    val expected = Reference.runRelay(config, priors, syndrome, beta)
    assert(!expected.success && expected.solutions == 0 && expected.iterations == 2)
    assert(expected.correction == expected.state.decision)
    assert(expected.residual == Reference.residual(graph, expected.state, syndrome))
    simulate(new RelayBpDecoder(
      config, Some(() => new TraceRelayCoefficients(beta)),
    )) { dut =>
      reset(dut)
      runRelay(dut, priors, syndrome, expected)
    }
  }

  "the production LFSRs drive a golden-model Relay run" in {
    val graph = nodes(3, Seq(Seq(0, 1, 2)))
    val config = RelayBpConfig(
      graph, initialIterations = 1, relayIterations = 1,
      maximumLegs = 4, solutionTarget = 1, seedOffset = 17,
    )
    val beta = Reference.lfsrBeta(3, config.maximumLegs, config.seedOffset)
    val priors = Vector.fill(3)(1)
    val syndrome = Vector(true)
    val expected = Reference.runRelay(config, priors, syndrome, beta)
    simulate(new RelayBpDecoder(config)) { dut =>
      reset(dut)
      runRelay(dut, priors, syndrome, expected)
      runRelay(dut, priors, syndrome, expected)
    }
  }

  "the hardware maximumLegs bound includes the initial leg" in {
    val graph = nodes(2, Seq(Seq(0, 1), Seq(0, 1)))
    val config = RelayBpConfig(
      graph, initialIterations = 1, relayIterations = 1,
      maximumLegs = 600, solutionTarget = 1,
    )
    val priors = Vector.fill(2)(1)
    val syndrome = Vector(true, false)
    val beta = Reference.lfsrBeta(2, config.maximumLegs, config.seedOffset)
    val expected = Reference.runRelay(config, priors, syndrome, beta)
    assert(!expected.success && expected.iterations == 600 && expected.legs == 600)
    simulate(new RelayBpDecoder(config)) { dut =>
      reset(dut)
      runRelay(dut, priors, syndrome, expected)
    }
  }

  "matches the pinned trmue oracle fixture at the algorithmic boundary" in {
    val graph = nodes(3, Seq(Seq(0, 1), Seq(1, 2)))
    val config = RelayBpConfig(
      graph, initialIterations = 10, relayIterations = 5,
      maximumLegs = 2, solutionTarget = 1,
    )
    val beta = Vector(Vector.fill(3)(7), Vector(6, 6, 5))
    val priors = Vector.fill(3)(4)
    val syndrome = Vector(true, true)
    val expected = Reference.runRelay(config, priors, syndrome, beta)
    assert(expected.success && expected.correction == Vector(false, true, false))
    simulate(new RelayBpDecoder(
      config, Some(() => new TraceRelayCoefficients(beta)),
    )) { dut =>
      reset(dut)
      runRelay(dut, priors, syndrome, expected)
    }
  }
}
