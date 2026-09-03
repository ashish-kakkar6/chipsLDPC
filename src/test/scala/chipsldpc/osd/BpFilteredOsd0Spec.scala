package chipsldpc.osd

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import chipsldpc.graph.{TannerGraph, TannerNodeGraphs}
import org.scalatest.freespec.AnyFreeSpec

final class BpFilteredOsd0Spec extends AnyFreeSpec with ChiselSim {
  private val graph = TannerGraph.fromRows(
    7,
    Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)),
  )
  private val nodes = TannerNodeGraphs.from(graph)
  private val config = BpFilteredOsd0Config(
    nodes, iterations = 30, threshold = 1, prefixes = Seq(7),
  )
  private def run(
      dut: BpFilteredOsd0,
      priors: Vector[Int],
      syndrome: Int,
      scope: Option[Set[Int]] = None,
      resultStalls: Int = 0,
  ): Unit = {
    val syndromeBits = Vector.tabulate(graph.checkCount)(row => (syndrome & 1 << row) != 0)
    val expected = BpFilteredOsd0Reference.run(config, priors, syndromeBits, scope)
    val expectedStatus = expected.status match {
      case 0 => DecodeStatus.BpConverged
      case 1 => DecodeStatus.OsdSolved
      case 2 => DecodeStatus.OsdInconsistent
      case 3 => DecodeStatus.OsdOverflow
    }

    dut.io.in.bits.syndrome.zip(syndromeBits).foreach { case (port, value) => port.poke(value.B) }
    dut.io.in.bits.prior.zip(priors).foreach { case (port, value) => port.poke(value.U) }
    dut.io.in.bits.inScopeValid.poke(scope.nonEmpty.B)
    dut.io.in.bits.inScope.zipWithIndex.foreach { case (port, i) => port.poke(scope.forall(_(i)).B) }
    dut.io.in.valid.poke(true.B)
    dut.io.result.ready.poke((resultStalls == 0).B)
    dut.io.in.ready.expect(true.B)
    dut.clock.step()
    dut.io.in.valid.poke(false.B)

    val correction = Vector.newBuilder[(Int, Int)]
    var elapsed = 0
    while (!dut.io.result.valid.peek().litToBoolean && elapsed < 1024) {
      if (dut.io.correction.valid.peek().litToBoolean) correction += (
        dut.io.correction.bits.index.peek().litValue.toInt ->
          dut.io.correction.bits.value.peek().litValue.toInt
      )
      dut.clock.step()
      elapsed += 1
    }
    dut.io.result.valid.expect(true.B)
    dut.io.result.bits.status.expect(expectedStatus)
    dut.io.result.bits.iterations.expect(expected.iterations.U)
    dut.io.result.bits.bpCycles.expect(expected.bpCycles.U)
    dut.io.result.bits.osdCycles.expect(expected.osdCycles.U)
    dut.io.result.bits.selected.expect(expected.selected.U)
    dut.io.result.bits.activeRows.expect(expected.activeRows.U)
    dut.io.result.bits.solverCycles.expect(expected.solverCycles.U)
    dut.io.result.bits.cycles.expect(expected.cycles.U)
    dut.io.soft.zip(expected.soft).foreach { case (port, value) => port.expect(value.S) }
    assert(elapsed == expected.cycles)

    val observed = correction.result()
    assert(observed == expected.correction)
    for (_ <- 0 until resultStalls) {
      dut.clock.step()
      dut.io.result.valid.expect(true.B)
      dut.io.result.bits.cycles.expect(elapsed.U)
    }
    dut.io.result.ready.poke(true.B)
    dut.clock.step()
  }

  "runs 30 complete iterations, exits early, and falls back without a controller round trip" in {
    simulate(new BpFilteredOsd0(config)) { dut =>
      dut.io.in.valid.poke(false.B)
      dut.io.correction.ready.poke(true.B)
      dut.io.result.ready.poke(true.B)

      run(dut, Vector.fill(7)(2), syndrome = 0)
      run(dut, Vector.fill(7)(0), syndrome = 5)
      run(dut, Vector.fill(7)(0), syndrome = 1, scope = Some(Set(0)))
      run(dut, Vector.fill(7)(0), syndrome = 1, scope = Some(Set(6)), resultStalls = 3)
    }
  }
}
