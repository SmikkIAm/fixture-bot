from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class Player:
    id: int
    first_name: str
    last_name: str
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def display_name(self) -> str:
        if self.first_name and self.last_name:
            return self.full_name
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        else:
            return f"Player {self.id}"
    
    def __post_init__(self):
        if self.id <= 0:
            raise ValueError("Player ID must be positive")
        
        if not self.first_name and not self.last_name:
            raise ValueError("Player must have at least a first name or last name")
    
    @classmethod
    def from_api_data(cls, api_data: Dict[str, Any]) -> "Player":
        return cls(
            id=api_data.get("ID", 0),
            first_name=api_data.get("FirstName", "").strip(),
            last_name=api_data.get("LastName", "").strip(),
        )
    
    @classmethod
    def create_fallback(cls, player_id: int) -> "Player":
        return cls(
            id=player_id,
            first_name=f"Player {player_id}",
            last_name="",
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "display_name": self.display_name,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Player":
        return cls(
            id=data["id"],
            first_name=data["first_name"],
            last_name=data["last_name"],
        )
    
    def __str__(self) -> str:
        return f"Player({self.id}: {self.display_name})"
    
    def __repr__(self) -> str:
        return (
            f"Player(id={self.id}, first_name='{self.first_name}', "
            f"last_name='{self.last_name}')"
        )
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.id == other.id
    
    def __hash__(self) -> int:
        return hash(self.id)