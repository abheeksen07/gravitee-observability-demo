"""Independent bounded budgets; full request population remains in metrics."""
class Budget:
    def __init__(self, rate):
        self.rate=rate/60; self.capacity=max(1,self.rate*5); self.tokens=self.capacity; self.last=None
    def take(self, now):
        if self.last is not None: self.tokens=min(self.capacity,self.tokens+max(0,now-self.last)*self.rate)
        self.last=max(self.last if self.last is not None else now,now)
        if self.tokens<1: return False
        self.tokens-=1; return True
class Sampler:
    def __init__(self):
        self.error=Budget(90); self.slow=Budget(90); self.normal=Budget(18)
    def take(self, req):
        return (self.error if req.status>=500 else self.slow if req.duration>=1 else self.normal).take(req.end)
