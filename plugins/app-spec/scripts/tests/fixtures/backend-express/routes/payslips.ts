import { Router } from 'express';
import { Controller, Get, Post } from '@nestjs/common';

const router = Router();

router.get('/employees/:id/payslips', requireAuth, async (req, res) => {
  res.json([]);
});

router.post("/employees/:id/payslips/refresh", (req, res) => res.sendStatus(202));

@Controller('employee/api/v1')
export class ReportsController {
  @Get('reports/:reportId')
  find() {}

  @Post('reports')
  create() {}
}

export default router;
