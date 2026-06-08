"""
ui/forms/traj_form.py - TRAJ (Aerator Trajectory) form.

Wired to em_traj.compute_trajectory() for jet trajectory + air flow rate.
"""
from __future__ import annotations
import math
from PySide6 import QtCore, QtWidgets
from ui.charts.matplotlib_widget import MplCanvas
from em_traj import (RampGeometry, FlowProperties, VentGeometry, compute_trajectory)


class TRAJForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TRAJ - Aerator Trajectory")
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)

        gb_flow = QtWidgets.QGroupBox("Water flow properties")
        gl = QtWidgets.QFormLayout(gb_flow)
        self.q = self._spin(283.168, 0, 1e6, "%.3f")
        self.vel_ramp = self._spin(35.0, 0, 100, "%.3f")
        self.depth_ramp = self._spin(1.5, 0, 50, "%.3f")
        self.turb = self._spin(0.05, 0, 0.5, "%.4f")
        gl.addRow("Discharge Q (m^3/s):", self.q)
        gl.addRow("Velocity at ramp (m/s):", self.vel_ramp)
        gl.addRow("Flow depth at ramp (m):", self.depth_ramp)
        gl.addRow("Turbulence intensity:", self.turb)
        lv.addWidget(gb_flow)

        gb_vent = QtWidgets.QGroupBox("Air vent geometry")
        vl = QtWidgets.QFormLayout(gb_vent)
        self.n_vents = QtWidgets.QSpinBox(); self.n_vents.setRange(0, 20); self.n_vents.setValue(2)
        self.vent_w = self._spin(1.5, 0, 20, "%.3f")
        self.vent_a = self._spin(3.0, 0, 100, "%.3f")
        self.vent_loss = self._spin(0.5, 0, 5, "%.3f")
        vl.addRow("Number of vents:", self.n_vents)
        vl.addRow("Vent width (m):", self.vent_w)
        vl.addRow("Vent area (m^2):", self.vent_a)
        vl.addRow("Loss coefficient:", self.vent_loss)
        lv.addWidget(gb_vent)

        gb_ramp = QtWidgets.QGroupBox("Ramp geometry")
        rl = QtWidgets.QFormLayout(gb_ramp)
        self.ramp_angle = self._spin(8.0, -45, 45, "%.2f")
        self.ramp_elev = self._spin(1000.0, -100, 10000, "%.3f")
        self.ramp_sta = self._spin(800.0, 0, 10000, "%.3f")
        self.floor_elev = self._spin(995.0, -100, 10000, "%.3f")
        rl.addRow("Ramp angle (deg):", self.ramp_angle)
        rl.addRow("Ramp lip elevation (m):", self.ramp_elev)
        rl.addRow("Ramp lip station (m):", self.ramp_sta)
        rl.addRow("Downstream floor elev (m):", self.floor_elev)
        lv.addWidget(gb_ramp)

        btn = QtWidgets.QPushButton("Compute")
        btn.clicked.connect(self._compute)
        lv.addWidget(btn)
        lv.addStretch(1)

        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        self.canvas = MplCanvas(width=7, height=5, dpi=100)
        rv.addWidget(self.canvas)
        self.results = QtWidgets.QTextEdit()
        self.results.setReadOnly(True)
        self.results.setMaximumHeight(120)
        rv.addWidget(self.results)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.status = QtWidgets.QLabel("Set parameters and click Compute.")
        layout.addWidget(self.status)

    def _spin(self, val, lo, hi, fmt):
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setDecimals(4)
        return s

    def _compute(self):
        ramp = RampGeometry(
            angle_deg=self.ramp_angle.value(),
            elev_lip=self.ramp_elev.value(),
            sta_lip=self.ramp_sta.value(),
            elev_floor=self.floor_elev.value(),
        )
        flow = FlowProperties(
            q=self.q.value(),
            velocity_ramp=self.vel_ramp.value(),
            depth_ramp=self.depth_ramp.value(),
            turbulence=self.turb.value(),
        )
        vent = VentGeometry(
            n_vents=self.n_vents.value(),
            width=self.vent_w.value(),
            area=self.vent_a.value(),
            loss_coeff=self.vent_loss.value(),
        )
        try:
            res = compute_trajectory(ramp, flow, vent)
            if not res.success:
                self.status.setText(f"Error: {res.error_message}")
                return
            self._plot(ramp, res)
            self.results.setPlainText(
                f"Jet landing station: {res.land_x:.2f} m\n"
                f"Range: {res.land_x - ramp.sta_lip:.2f} m\n"
                f"Flight time: {res.land_t:.3f} s\n"
                f"Max height above lip: {res.max_height - ramp.elev_lip:.3f} m\n"
                f"Required V_air: {res.air_velocity_required:.2f} m/s\n"
                f"Required Q_air: {res.air_flow_rate:.2f} m^3/s\n"
                f"Submergence required: {res.submergence_required:.3f} m"
            )
            self.status.setText(f"Computed: range={res.land_x - ramp.sta_lip:.1f} m, Q_air={res.air_flow_rate:.2f} m^3/s")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status.setText(f"Error: {e}")

    def _plot(self, ramp, res):
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        xs = [p.x for p in res.trajectory]
        ys = [p.y for p in res.trajectory]
        ax.plot(xs, ys, 'b-', linewidth=2, label=f'Jet trajectory (angle {ramp.angle_deg:.1f}°)')
        ax.fill_between(xs, [y - res.jet_thickness for y in ys], ys, color='cyan', alpha=0.3, label='Jet thickness')
        ax.plot(ramp.sta_lip, ramp.elev_lip, 'go', markersize=10, label='Ramp lip')
        if res.land_x != float("inf"):
            ax.plot(res.land_x, ramp.elev_floor, 'r*', markersize=15, label=f'Landing: STA={res.land_x:.1f}')
        ax.axhline(ramp.elev_floor, color='k', linestyle='--', alpha=0.4, label='Floor')
        ax.set_xlabel('Station (m)')
        ax.set_ylabel('Elevation (m)')
        ax.set_title(f'TRAJ: Jet Trajectory & Aerator Air Demand\nQ={res.trajectory[0] and ""} Q_air={res.air_flow_rate:.2f} m^3/s')
        ax.legend(loc='upper right', fontsize=9)
        ax.grid(True, alpha=0.3)
        self.canvas.draw()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = TRAJForm()
    w.show()
    sys.exit(app.exec())
