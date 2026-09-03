package chipsldpc.sort

import chisel3._
import chisel3.util.{Decoupled, Enum, log2Ceil}

sealed trait NeighbourOrder
case object MagnitudeAscending extends NeighbourOrder
case object SignedAscending extends NeighbourOrder

final case class NeighbourSorterConfig(
    size: Int,
    softBits: Int,
    threshold: BigInt,
    order: NeighbourOrder = MagnitudeAscending,
) {
  require(size > 0, "size must be positive")
  require(softBits > 1, "softBits must exceed one")
  private val limit = BigInt(1) << (softBits - 1)
  order match {
    case MagnitudeAscending => require(threshold >= 0 && threshold <= limit + 1, "threshold is out of range")
    case SignedAscending => require(threshold >= -limit && threshold < limit, "threshold is out of range")
  }

  val pairs: Int = (size + 1) / 2
  val indexBits: Int = math.max(1, log2Ceil(size))
  val countBits: Int = math.max(1, log2Ceil(size + 1))
}

final class NeighbourSorterInput(config: NeighbourSorterConfig) extends Bundle {
  val soft = Vec(config.size, SInt(config.softBits.W))
  val inScopeValid = Bool()
  val inScope = Vec(config.size, Bool())
}

final class NeighbourSorterOutput(config: NeighbourSorterConfig) extends Bundle {
  val soft = SInt(config.softBits.W)
  val index = UInt(config.indexBits.W)
  val last = Bool()
}

private final class Entry(config: NeighbourSorterConfig) extends Bundle {
  val soft = SInt(config.softBits.W)
  val magnitude = UInt(config.softBits.W)
  val index = UInt(config.indexBits.W)
}

/** Section 3.1 sorter for one parallel BP-soft frame and an optional runtime scope. */
final class NeighbourSorter(config: NeighbourSorterConfig) extends Module {
  val io = IO(new Bundle {
    val in = Flipped(Decoupled(new NeighbourSorterInput(config)))
    val out = Decoupled(new NeighbourSorterOutput(config))
    val done = Output(Bool())
  })

  private val sIdle :: sFill :: sDrain :: Nil = Enum(3)
  private val state = RegInit(sIdle)
  private val soft = Reg(Vec(config.size, SInt(config.softBits.W)))
  private val inScopeValid = Reg(Bool())
  private val inScope = Reg(Vec(config.size, Bool()))
  private val scan = RegInit(0.U(config.indexBits.W))
  private val count = RegInit(0.U(config.countBits.W))
  private val remaining = RegInit(0.U(config.countBits.W))
  private val left = Reg(Vec(config.pairs, new Entry(config)))
  private val right = Reg(Vec(config.pairs, new Entry(config)))
  private val leftValid = RegInit(VecInit(Seq.fill(config.pairs)(false.B)))
  private val rightValid = RegInit(VecInit(Seq.fill(config.pairs)(false.B)))
  private val done = RegInit(false.B)

  private def included(value: SInt): Bool = config.order match {
    case MagnitudeAscending => value.abs.asUInt < config.threshold.U
    case SignedAscending => value < config.threshold.S(config.softBits.W)
  }

  private def precedes(a: Entry, b: Entry): Bool = {
    val less = config.order match {
      case MagnitudeAscending => a.magnitude < b.magnitude
      case SignedAscending => a.soft < b.soft
    }
    val equal = config.order match {
      case MagnitudeAscending => a.magnitude === b.magnitude
      case SignedAscending => a.soft === b.soft
    }
    less || (equal && a.index <= b.index)
  }

  io.in.ready := state === sIdle
  io.out.valid := state === sDrain && leftValid.head
  io.out.bits.soft := left.head.soft
  io.out.bits.index := left.head.index
  io.out.bits.last := remaining === 1.U
  io.done := done
  done := false.B

  when(io.in.fire) {
    val firstSoft = io.in.bits.soft(config.size - 1)
    val firstMagnitude = firstSoft.abs.asUInt
    val firstInclude = included(firstSoft) &&
      (!io.in.bits.inScopeValid || io.in.bits.inScope(config.size - 1))
    for (i <- 0 until config.size) {
      soft(i) := io.in.bits.soft(i)
      inScope(i) := io.in.bits.inScope(i)
    }
    inScopeValid := io.in.bits.inScopeValid
    leftValid.foreach(_ := false.B)
    rightValid.foreach(_ := false.B)
    when(firstInclude) {
      left.head.soft := firstSoft
      left.head.magnitude := firstMagnitude
      left.head.index := (config.size - 1).U
      leftValid.head := true.B
    }
    count := firstInclude.asUInt
    if (config.size == 1) {
      when(firstInclude) {
        remaining := 1.U
        state := sDrain
      }.otherwise {
        done := true.B
        state := sIdle
      }
    } else {
      scan := (config.size - 2).U
      state := sFill
    }
  }.elsewhen(state === sFill) {
    val currentSoft = if (config.size == 1) soft.head else soft(scan)
    val currentScope = if (config.size == 1) inScope.head else inScope(scan)
    val magnitude = currentSoft.abs.asUInt
    val include = included(currentSoft) && (!inScopeValid || currentScope)
    val nextCount = count + include.asUInt
    val candidate = Wire(new Entry(config))
    candidate.soft := currentSoft
    candidate.magnitude := magnitude
    candidate.index := scan

    when(include) {
      for (i <- 0 until config.pairs) {
        val carry = if (i == 0) candidate else right(i - 1)
        val carryValid = if (i == 0) true.B else rightValid(i - 1)
        rightValid(i) := false.B
        when(carryValid) {
          when(!leftValid(i) || precedes(carry, left(i))) {
            left(i) := carry
            leftValid(i) := true.B
            right(i) := left(i)
            rightValid(i) := leftValid(i)
          }.otherwise {
            right(i) := carry
            rightValid(i) := true.B
          }
        }
      }
    }

    count := nextCount
    when(scan === 0.U) {
      when(nextCount === 0.U) {
        done := true.B
        state := sIdle
      }.otherwise {
        remaining := nextCount
        state := sDrain
      }
    }.otherwise {
      scan := scan - 1.U
    }
  }.elsewhen(io.out.fire) {
    for (i <- 0 until config.pairs) {
      val carry = if (i + 1 < config.pairs) left(i + 1) else 0.U.asTypeOf(new Entry(config))
      val carryValid = if (i + 1 < config.pairs) leftValid(i + 1) else false.B
      leftValid(i) := false.B
      when(!rightValid(i)) {
        right(i) := carry
        rightValid(i) := carryValid
      }.elsewhen(!carryValid) {
        left(i) := right(i)
        leftValid(i) := true.B
        rightValid(i) := false.B
      }.elsewhen(precedes(right(i), carry)) {
        left(i) := right(i)
        leftValid(i) := true.B
        right(i) := carry
      }.otherwise {
        left(i) := carry
        leftValid(i) := true.B
      }
    }

    when(remaining === 1.U) {
      remaining := 0.U
      done := true.B
      state := sIdle
    }.otherwise {
      remaining := remaining - 1.U
    }
  }
}
