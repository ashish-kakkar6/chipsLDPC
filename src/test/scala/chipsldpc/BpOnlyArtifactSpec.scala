package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec

private object BpOnlyArtifactSpec {
  final case class Expected(
      state: Reference.DecoderState,
      iterations: Int,
      converged: Boolean,
      indices: Vector[Int],
      cycles: Int,
  )
}

final class BpOnlyArtifactSpec extends AnyFreeSpec with ChiselSim {
  import BpOnlyArtifactSpec.Expected

  private val problem = DecoderProblem.parse(
    """{"schema":1,"n":7,"row_ones":[[3,4,5,6],[1,2,5,6],[0,2,4,6]],"prior":[1,2,3,4,5,6,7],"syndrome":[1,0,1],"iterations":4}""",
  )
  private val streamConfig = SparseBitmaskStreamerConfig(problem.n)

  private def model(priors: Vector[Int], syndrome: Vector[Boolean]): Expected = {
    var state = Reference.initialize(problem.nodes, priors, RelayDefaults.q)
    var iterations = 0
    var converged = false
    while (iterations < problem.iterations && !converged) {
      iterations += 1
      state = Reference.iterate(
        problem.nodes, state, syndrome, priors, problem.control(iterations),
        RelayDefaults.q, RelayDefaults.scale,
      )
      converged = !Reference.residual(problem.nodes, state, syndrome).contains(true)
    }
    val indices = state.decision.zipWithIndex.collect { case (true, index) => index }
    val occupiedBanks = indices.map(_ / streamConfig.bankWidth).distinct.size
    Expected(state, iterations, converged, indices,
      2 * iterations + 1 + occupiedBanks + indices.size)
  }

  private def packBits(bits: Seq[Boolean]): BigInt =
    bits.zipWithIndex.foldLeft(BigInt(0)) { case (value, (bit, index)) =>
      if (bit) value.setBit(index) else value
    }

  private def packPriors(priors: Seq[Int]): BigInt =
    priors.zipWithIndex.foldLeft(BigInt(0)) { case (value, (prior, index)) =>
      value | BigInt(prior) << (index * RelayDefaults.q.magnitudeBits)
    }

  private def signedField(value: BigInt, index: Int): Int = {
    val width = RelayDefaults.q.accumulatorBits
    val field = (value >> (index * width)) & ((BigInt(1) << width) - 1)
    if (field.testBit(width - 1)) (field - (BigInt(1) << width)).toInt else field.toInt
  }

  private def run(
      dut: BpOnlyArtifact,
      priors: Vector[Int],
      syndrome: Vector[Boolean],
      expected: Expected,
      correctionReady: Int => Boolean = _ => true,
      resultHoldCycles: Int = 0,
  ): Unit = {
    dut.syndrome.poke(packBits(syndrome).U)
    dut.prior.poke(packPriors(priors).U)
    dut.inputValid.poke(true.B)
    dut.inputReady.expect(true.B)
    dut.clock.step()
    dut.inputValid.poke(false.B)

    val observed = Vector.newBuilder[Int]
    var elapsed = 0
    var accepted = 0
    var stalls = 0
    var held = Option.empty[(Int, Boolean)]
    while (!dut.resultValid.peek().litToBoolean && elapsed < 128) {
      val ready = correctionReady(elapsed)
      dut.correctionReady.poke(ready.B)
      val valid = dut.correctionValid.peek().litToBoolean
      if (valid) {
        dut.correctionValue.expect(true.B)
        val index = dut.correctionIndex.peek().litValue.toInt
        val last = dut.correctionLast.peek().litToBoolean
        held.foreach(entry => assert(entry == (index, last)))
        if (ready) {
          assert(accepted < expected.indices.size)
          assert(index == expected.indices(accepted))
          assert(last == (accepted == expected.indices.size - 1))
          observed += index
          accepted += 1
          held = None
        } else {
          held = Some(index -> last)
          stalls += 1
        }
      } else {
        assert(held.isEmpty)
      }
      dut.clock.step()
      elapsed += 1
    }

    assert(elapsed < 128)
    assert(observed.result() == expected.indices)
    assert(elapsed == expected.cycles + stalls)
    dut.resultValid.expect(true.B)
    dut.status.expect((if (expected.converged) 0 else 2).U)
    dut.completedIterations.expect(expected.iterations.U)
    dut.cycles.expect((expected.cycles + stalls).U)
    dut.bpCycles.expect((2 * expected.iterations).U)
    val soft = dut.softOutput.peek().litValue
    expected.state.marginal.indices.foreach { index =>
      assert(signedField(soft, index) == expected.state.marginal(index))
    }
    dut.resultReady.poke(false.B)
    dut.correctionValid.expect(false.B)
    for (_ <- 0 until resultHoldCycles) {
      dut.clock.step()
      dut.resultValid.expect(true.B)
      dut.correctionValid.expect(false.B)
      dut.cycles.expect((expected.cycles + stalls).U)
    }
    dut.resultReady.poke(true.B)
    dut.clock.step()
    dut.inputReady.expect(true.B)
  }

  "accounts for correction stalls and holds a completed result" in {
    val priors = Vector.fill(problem.n)(1)
    val syndrome = Vector(true, false, false)
    val expected = model(priors, syndrome)
    assert(expected.indices.size == 1)

    simulate(new BpOnlyArtifact(problem)) { dut =>
      dut.inputValid.poke(false.B)
      dut.iterationLimit.poke(problem.iterations.U)
      dut.scopeValid.poke(false.B)
      dut.scope.poke(0.U)
      dut.correctionReady.poke(true.B)
      dut.resultReady.poke(true.B)
      dut.reset.poke(true.B)
      dut.clock.step()
      dut.reset.poke(false.B)

      run(
        dut, priors, syndrome, expected,
        correctionReady = cycle => cycle != expected.cycles - 1,
        resultHoldCycles = 3,
      )
    }
  }

  "matches the independent BP model for empty and sparse corrections" in {
    val frames = Seq(
      Vector.fill(problem.n)(2) -> Vector.fill(problem.graph.checkCount)(false),
      Vector.fill(problem.n)(1) -> Vector(true, false, false),
    ).map { case (priors, syndrome) => (priors, syndrome, model(priors, syndrome)) }
    assert(frames.head._3.indices.isEmpty)
    assert(frames.last._3.indices.nonEmpty)

    simulate(new BpOnlyArtifact(problem)) { dut =>
      dut.inputValid.poke(false.B)
      dut.iterationLimit.poke(problem.iterations.U)
      dut.scopeValid.poke(false.B)
      dut.scope.poke(0.U)
      dut.correctionReady.poke(true.B)
      dut.resultReady.poke(true.B)
      dut.reset.poke(true.B)
      dut.clock.step()
      dut.reset.poke(false.B)

      frames.foreach { case (priors, syndrome, expected) =>
        run(dut, priors, syndrome, expected)
      }
    }
  }

  "writes the independent BP result as a sparse golden stream" in {
    val cases = Seq(
      problem.copy(
        prior = Vector.fill(problem.n)(2),
        syndrome = Vector.fill(problem.graph.checkCount)(false),
      ),
      problem.copy(
        prior = Vector.fill(problem.n)(1),
        syndrome = Vector(true, false, false),
      ),
    )
    cases.foreach { current =>
      val expected = model(current.prior, current.syndrome)
      val lines = BpOnlyExperiment.golden(current).linesIterator.toVector
      val result = lines(3).split(' ').map(_.toInt).toVector
      val stream = lines(5).split(' ').map(_.toInt).toVector
      assert(result.take(4) == Vector(
        if (expected.converged) 0 else 2,
        expected.iterations,
        expected.cycles,
        2 * expected.iterations,
      ))
      assert(stream == Vector(expected.indices.size) ++
        expected.indices.flatMap(index => Vector(index, 1)))
    }
  }
}
