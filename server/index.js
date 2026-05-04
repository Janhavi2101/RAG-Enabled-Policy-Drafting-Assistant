const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const multer = require('multer');
const fs = require('fs');
const axios = require('axios');
const FormData = require('form-data');
require('dotenv').config();

const app = express();
const upload = multer({ dest: 'uploads/' });
const AI_ENGINE_URL = process.env.AI_ENGINE_URL || 'http://127.0.0.1:5001';

app.use(cors());
app.use(express.json());

// --- MONGODB CONNECTION ---
mongoose.connect(process.env.MONGODB_URI)
  .then(() => console.log('MongoDB Connected'))
  .catch(err => console.error('Mongo Error:', err));

// --- MONGODB SCHEMA ---
const PolicySchema = new mongoose.Schema({
  title: String,
  department: String,
  uploadDate: { type: Date, default: Date.now },
  filename: String
});
const Policy = mongoose.model('Policy', PolicySchema);

// --- Helper: Call Ollama API ---
async function callOllama(model, messages, temperature = 0.3) {
  try {
    const res = await axios.post('http://localhost:11434/v1/chat/completions', {
      model,
      messages,
      temperature
    });
    return res.data.choices?.[0]?.message?.content || '';
  } catch (err) {
    console.error('Ollama API Error:', err.message);
    throw new Error('AI Service unavailable');
  }
}

// 1. Upload & Save Policy Metadata
app.post('/api/upload-policy', upload.single('file'), async (req, res) => {
  try {
    const { path, originalname } = req.file;
    const metadata = JSON.parse(req.body.metadata || '{}');

    const newPolicy = new Policy({
      title: metadata.policyName || originalname,
      department: metadata.department || 'General',
      filename: originalname
    });
    await newPolicy.save();

    // Cleanup local file
    fs.unlinkSync(path);

    res.json({ success: true, message: 'Policy uploaded successfully.' });
  } catch (error) {
    console.error('Upload Error:', error);
    res.status(500).json({ success: false, message: 'Upload failed.', error: String(error) });
  }
});

// 2. Chat / Search using gemma:2b
app.post('/api/search', async (req, res) => {
  try {
    const query = req.body.query;
    const messages = [
      { role: 'system', content: 'You are a helpful legal assistant.' },
      { role: 'user', content: query }
    ];

    const output = await callOllama('gemma:2b', messages);
    res.json({ message: output });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

// 3. Draft Generation using mistral:latest
app.post('/api/draft', async (req, res) => {
  try {
    const response = await axios.post(`${AI_ENGINE_URL}/draft`, {
      query: req.body.query,
      current_content: req.body.current_content || ''
    });
    res.json({
      message: response.data?.response || 'Drafting service returned an empty response.'
    });
  } catch (error) {
    console.error('Draft proxy error:', error.message);
    res.status(500).json({ message: 'Drafting service unavailable' });
  }
});

// 4. Conflict Check (placeholder - could integrate AI later)
app.post('/api/check-policy-conflict', upload.single('file'), async (req, res) => {
  try {
    // For now, just remove the uploaded file and return dummy result
    fs.unlinkSync(req.file.path);
    res.json({
      hasConflict: false,
      message: 'Conflict check not implemented yet.',
      suggestions: []
    });
  } catch (error) {
    console.error('Conflict Check Error:', error);
    res.status(500).json({ hasConflict: false, message: 'Conflict check failed.', error: String(error) });
  }
});

// 5. Draft Validation proxy
app.post('/api/validate-policy-pdf', upload.single('file'), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'No file uploaded.' });
  }

  const cleanupTempFile = () => {
    if (req.file?.path && fs.existsSync(req.file.path)) {
      fs.unlinkSync(req.file.path);
    }
  };

  try {
    const fileName = req.file.originalname || '';
    if (!fileName.toLowerCase().endsWith('.pdf')) {
      cleanupTempFile();
      return res.status(400).json({ error: 'Only PDF files are supported.' });
    }

    const formData = new FormData();
    formData.append('file', fs.createReadStream(req.file.path), {
      filename: req.file.originalname,
      contentType: req.file.mimetype || 'application/pdf',
    });

    const response = await axios.post(`${AI_ENGINE_URL}/validate-policy-pdf`, formData, {
      headers: formData.getHeaders(),
      maxContentLength: Infinity,
      maxBodyLength: Infinity,
      validateStatus: () => true,
    });

    cleanupTempFile();
    return res.status(response.status).json(response.data);
  } catch (error) {
    cleanupTempFile();
    console.error('Draft validation proxy error:', error.message);
    return res.status(500).json({ error: 'Draft validation service unavailable.' });
  }
});

const PORT = 4000;
app.listen(PORT, () => console.log(`Node Server running on ${PORT}`));
