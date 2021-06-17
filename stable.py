import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from itertools import product


class JSONCapability:
    def to_json(self):
        return {
            k: v if not isinstance(v, Vector) else str(v)
            for k, v in self.__dict__.items() if v is not None
        }


# region primitives
@dataclass
class Vector:
    X: int
    Y: int
    Z: int

    @classmethod
    def from_json(cls, data):
        x, y, z = map(int, data.split('/'))
        return cls(x, y, z)

    def __str__(self):
        return f"{self.X}/{self.Y}/{self.Z}"

    def __add__(self, other: 'Vector'):
        return Vector(self.X + other.X, self.Y + other.Y, self.Z + other.Z)

    def __sub__(self, other: 'Vector'):
        return self + other * -1

    def __mul__(self, coefficient: int) -> 'Vector':
        return Vector(self.X * coefficient, self.Y * coefficient, self.Z * coefficient)

    def clen(self, other: 'Vector') -> int:
        return max(abs(self.X - other.X), abs(self.Y - other.Y), abs(self.Z - other.Z))

    def __hash__(self):
        return hash((self.X, self.Y, self.Z))

    def __eq__(self, other: 'Vector') -> bool:
        return (self.X, self.Y, self.Z) == (other.X, other.Y, other.Z)

    def in_bounds(self) -> bool:
        return all(ship_size * player_id < c < map_size - ship_size * (1 - player_id)
                   for c in (self.X, self.Y, self.Z))


# endregion

# region battle commands

@dataclass
class CommandParameters(JSONCapability):
    pass


@dataclass
class AttackCommandParameters(CommandParameters):
    Id: int
    Name: str
    Target: Vector


@dataclass
class MoveCommandParameters(CommandParameters):
    Id: int
    Target: Vector


@dataclass
class AccelerateCommandParameters(CommandParameters):
    Id: int
    Vector: Vector


@dataclass
class UserCommand(JSONCapability):
    Command: str
    Parameters: CommandParameters


@dataclass
class BattleOutput(JSONCapability):
    Message: str = None
    UserCommands: List[UserCommand] = None


# endregion

# region equipment

class EquipmentType(Enum):
    Energy = 0
    Gun = 1
    Engine = 2
    Health = 3


class EffectType(Enum):
    Blaster = 0


@dataclass
class EquipmentBlock(JSONCapability):
    Name: str
    Type: EquipmentType

    @classmethod
    def from_json(cls, data):
        if EquipmentType(data['Type']) == EquipmentType.Energy:
            return EnergyBlock(**data)
        elif EquipmentType(data['Type']) == EquipmentType.Gun:
            return GunBlock(**data)
        elif EquipmentType(data['Type']) == EquipmentType.Engine:
            return EngineBlock(**data)
        elif EquipmentType(data['Type']) == EquipmentType.Health:
            return HealthBlock(**data)


@dataclass
class EnergyBlock(EquipmentBlock):
    IncrementPerTurn: int
    MaxEnergy: int
    StartEnergy: int
    Type = EquipmentType.Energy


@dataclass
class EngineBlock(EquipmentBlock):
    MaxAccelerate: int
    Type = EquipmentType.Engine


@dataclass
class GunBlock(EquipmentBlock):
    Damage: int
    EffectType: EffectType
    EnergyPrice: int
    Radius: int
    Type = EquipmentType.Gun


@dataclass
class HealthBlock(EquipmentBlock):
    MaxHealth: int
    StartHealth: int


@dataclass
class EffectType(EquipmentBlock):
    MaxHealth: int
    StartHealth: int
    Type = EquipmentType.Health


# endregion

# region battle state

@dataclass
class Ship(JSONCapability):
    Id: int
    Position: Vector
    Velocity: Vector
    Energy: Optional[int] = None
    Health: Optional[int] = None
    Equipment: List[EquipmentBlock] = None

    @classmethod
    def from_json(cls, data):
        if data.get('Equipment'):
            data['Equipment'] = list(map(EquipmentBlock.from_json, data.get('Equipment', [])))
        data['Position'] = Vector.from_json(data['Position'])
        data['Velocity'] = Vector.from_json(data['Velocity'])
        return cls(**data)


@dataclass
class FireInfo(JSONCapability):
    EffectType: EffectType
    Source: Vector
    Target: Vector

    @classmethod
    def from_json(cls, data):
        data['Source'] = Vector.from_json(data['Source'])
        data['Target'] = Vector.from_json(data['Target'])
        return cls(**data)


@dataclass
class BattleState(JSONCapability):
    FireInfos: List[FireInfo]
    My: List[Ship]
    Opponent: List[Ship]

    @classmethod
    def from_json(cls, data):
        my = list(map(Ship.from_json, data['My']))
        opponent = list(map(Ship.from_json, data['Opponent']))
        fire_infos = list(map(FireInfo.from_json, data['FireInfos']))
        return cls(fire_infos, my, opponent)


# endregion


def make_draft(data: dict) -> dict:
    global player_id
    player_id = int(data['PlayerId'])
    return {}


def make_turn(data: dict) -> BattleOutput:
    # TODO: move some actions to draft stage
    global target

    battle_state = BattleState.from_json(data)
    battle_output = BattleOutput()
    battle_output.UserCommands = []
    moves = set()

    for ship in battle_state.My:
        if target is None or target not in battle_state.Opponent:
            target = min(battle_state.Opponent,
                         key=lambda o: (ship.Position.clen(o.Position), o.Health))
        else:
            # updating target position
            target = next(filter(lambda o: o == target, battle_state.Opponent))

        engine = next(filter(lambda e: isinstance(e, EngineBlock), ship.Equipment), None)
        if engine is not None:
            pos_black_list = set()
            for x, y, z in product((0, ship_size // 2, -ship_size // 2), repeat=3):
                dv = Vector(x, y, z)
                pos_black_list |= {opponent.Position + opponent.Velocity + dv
                                   for opponent in battle_state.Opponent} #| \
                    # {fire.Target + dv for fire in battle_state.FireInfos}

            step = engine.MaxAccelerate

            positions_set = set(filter(
                Vector.in_bounds,
                map(lambda p: ship.Position + Vector(*p), product((0, step, -step), repeat=3)))
            ) - pos_black_list - moves

            if positions_set:
                target_pos = min(
                    positions_set,
                    key=lambda v: abs(5 - target.Position.clen(v)) + sum(map(
                        lambda o: o.Position.clen(v) < 6,
                        filter(lambda e: e.Id != target.Id, battle_state.Opponent)
                    ))
                )

                moves |= set(map(lambda p: target_pos + Vector(*p),
                                 product((0, ship_size // 2, -ship_size // 2), repeat=3)))

                battle_output.UserCommands.append(
                    UserCommand(
                        Command='MOVE', Parameters=MoveCommandParameters(ship.Id, target_pos)
                    )
                )

        for gun in filter(lambda e: isinstance(e, GunBlock), ship.Equipment):
            aim = None
            r = gun.Radius

            if ship.Position.clen(target.Position + target.Velocity) <= r + ship_size:
                aim = target.Position + target.Velocity

            else:
                opponents = [
                    opponent for opponent in battle_state.Opponent
                    if ship.Position.clen(opponent.Position + opponent.Velocity) <= r + ship_size
                ]
                if opponents:
                    opponent = min(opponents, key=lambda o: o.Health)
                    aim = opponent.Position + opponent.Velocity

            if aim is not None:
                battle_output.UserCommands.append(
                    UserCommand(
                        Command='ATTACK', Parameters=AttackCommandParameters(ship.Id, gun.Name, aim)
                    )
                )
    return battle_output


def play_game():
    start = True
    while True:
        raw_line = input()
        line = json.loads(raw_line)
        if start:
            print(json.dumps(make_draft(line), default=lambda x: x.to_json(), ensure_ascii=False))
            start = False
        else:
            print(json.dumps(make_turn(line), default=lambda x: x.to_json(), ensure_ascii=False))


if __name__ == '__main__':
    player_id = 0
    # TODO: load variables from DraftOptions
    map_size = 30
    ship_size = 2
    target = None
    play_game()
